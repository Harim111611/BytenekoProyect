from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, CreateView
from django.urls import reverse, reverse_lazy
from django.shortcuts import redirect
from django.contrib import messages
from django.core.cache import cache
from django.db.models import Count, Prefetch
from django.core.exceptions import FieldError
from django.http import JsonResponse
from django.db import connection
from django.conf import settings

import json

from core.mixins import OwnerRequiredMixin, EncuestaQuerysetMixin
from surveys.models import Survey, Question, AnswerOption
from core.utils.logging_utils import StructuredLogger, log_user_action
import time

logger = StructuredLogger('surveys')


def _fast_delete_surveys(cursor, survey_ids):
    """
    Eliminación verdaderamente rápida usando Subqueries SQL puras.
    Evita traer IDs a la memoria de Python (round-trips innecesarios).
    Todo el trabajo se hace en la base de datos.
    """
    survey_ids = list(survey_ids)
    if not survey_ids:
        return

    # Preparamos los placeholders para los IDs de las encuestas
    placeholders = ','.join(['%s'] * len(survey_ids))
    params = survey_ids

    start_time = time.time()
    logger.info(f"[DELETE] 🚀 INICIANDO eliminación optimizada SQL de {len(survey_ids)} encuesta(s): {survey_ids}")
    # Log de prueba eliminado para evitar ruido en producción

    # Inicializar variables de tiempo para evitar errores si hay excepciones
    qr_time = sr_time = ao_time = q_time = s_time = 0.0
    qr_count = sr_count = ao_count = q_count = s_count = 0

    try:
        # PostgreSQL specific: deshabilitar triggers/constraints temporalmente.
        # Si esto falla por permisos, seguimos con el borrado estándar (respeta FKs pero más lento)
        try:
            cursor.execute("SET session_replication_role = 'replica'")
        except Exception:
            pass  # Ignorar si no tenemos permisos, la eliminación funcionará pero validará FKs

        # 1. Eliminar QuestionResponses (tabla grande) vía subconsulta
        step_start = time.time()
        cursor.execute(f"""
            DELETE FROM surveys_questionresponse
            WHERE survey_response_id IN (
                SELECT id FROM surveys_surveyresponse 
                WHERE survey_id IN ({placeholders})
            )
        """, params)
        qr_count = cursor.rowcount
        qr_time = time.time() - step_start
        logger.info(f"[DELETE] 📊 Step 1 - QuestionResponse: {qr_count} filas en {qr_time:.2f}s")

        # 2. Eliminar SurveyResponses
        step_start = time.time()
        cursor.execute(f"""
            DELETE FROM surveys_surveyresponse
            WHERE survey_id IN ({placeholders})
        """, params)
        sr_count = cursor.rowcount
        sr_time = time.time() - step_start
        logger.info(f"[DELETE] Step 2 - SurveyResponse: {sr_count} filas en {sr_time:.2f}s")

        # 3. Eliminar AnswerOptions (vía Question)
        step_start = time.time()
        cursor.execute(f"""
            DELETE FROM surveys_answeroption
            WHERE question_id IN (
                SELECT id FROM surveys_question 
                WHERE survey_id IN ({placeholders})
            )
        """, params)
        ao_count = cursor.rowcount
        ao_time = time.time() - step_start
        logger.info(f"[DELETE] Step 3 - AnswerOption: {ao_count} filas en {ao_time:.2f}s")

        # 4. Eliminar Questions
        step_start = time.time()
        cursor.execute(f"""
            DELETE FROM surveys_question
            WHERE survey_id IN ({placeholders})
        """, params)
        q_count = cursor.rowcount
        q_time = time.time() - step_start
        logger.info(f"[DELETE] Step 4 - Question: {q_count} filas en {q_time:.2f}s")

        # 5. Eliminar Surveys
        step_start = time.time()
        cursor.execute(f"""
            DELETE FROM surveys_survey
            WHERE id IN ({placeholders})
        """, params)
        s_count = cursor.rowcount
        s_time = time.time() - step_start
        logger.info(f"[DELETE] Step 5 - Survey: {s_count} filas en {s_time:.2f}s")

    except Exception as e:
        # Loguear y relanzar
        logger.error(f"[DELETE] ERROR durante eliminación: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        raise

    finally:
        # Restaurar integridad referencial
        try:
            cursor.execute("SET session_replication_role = 'origin'")
        except Exception:
            pass

    total_duration = time.time() - start_time
    logger.info(f"[DELETE] ✅ Eliminación completa: {len(survey_ids)} encuesta(s) en {total_duration:.2f}s")
    logger.info(
        f"[DELETE] Desglose: QR={qr_time:.2f}s ({qr_count} filas), "
        f"SR={sr_time:.2f}s ({sr_count} filas), "
        f"AO={ao_time:.2f}s ({ao_count} filas), "
        f"Q={q_time:.2f}s ({q_count} filas), "
        f"S={s_time:.2f}s ({s_count} filas)"
    )


# --- Bulk delete surveys ---
@login_required
@require_POST
def bulk_delete_surveys_view(request):
    """
    Eliminación bulk priorizando primero las encuestas pequeñas
    (menos respuestas) y usando un borrado SQL ultra-rápido cuando es posible.

    Compatible con:
    - Peticiones normales (POST de formulario): redirige con mensajes.
    - Peticiones AJAX (fetch con X-Requested-With=XMLHttpRequest): responde JSON.
    """
    survey_ids = request.POST.getlist('survey_ids')

    if not survey_ids:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse(
                {'success': False, 'error': 'No se seleccionaron encuestas para eliminar.'},
                status=400
            )
        messages.error(request, 'No se seleccionaron encuestas para eliminar.')
        return redirect('surveys:list')

    # Normalizamos los IDs
    try:
        clean_ids = [int(sid) for sid in survey_ids]
    except ValueError:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse(
                {'success': False, 'error': 'IDs de encuestas inválidos.'},
                status=400
            )
        messages.error(request, 'IDs de encuestas inválidos.')
        return redirect('surveys:list')

    # Solo encuestas del usuario actual (seguridad reforzada)
    base_qs = Survey.objects.filter(id__in=clean_ids, author=request.user)
    if not base_qs.exists():
        logger.warning(f"[BULK_DELETE][PERMISSION_DENIED] user_id={request.user.id} ids={clean_ids}")
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse(
                {'success': False, 'error': 'No tienes permisos para eliminar las encuestas seleccionadas.'},
                status=403
            )
        messages.error(request, 'No tienes permisos para eliminar las encuestas seleccionadas.')
        return redirect('surveys:list')

    # ---------------------------------------
    # Priorizar por tamaño (número de respuestas)
    # ---------------------------------------
    try:
        # Ajusta 'responses' si tu related_name es distinto
        qs_ordered = base_qs.annotate(
            num_respuestas=Count('responses')
        ).order_by('num_respuestas', 'id')
        using_annotation = True
    except FieldError:
        qs_ordered = base_qs.order_by('id')
        using_annotation = False

    ordered_ids = list(qs_ordered.values_list('id', flat=True))

    deleted_count = 0
    used_fast_path = False

    # Intento 1: ruta rápida SQL
    try:
        with connection.cursor() as cursor:
            _fast_delete_surveys(cursor, ordered_ids)
        deleted_count = len(ordered_ids)
        used_fast_path = True
        logger.info(
            f'[BULK_DELETE][SQL_FAST] Eliminadas {deleted_count} encuestas para user_id={request.user.id}. ordered_by_size={using_annotation} IDs={ordered_ids}'
        )
    except Exception as e:
        # Fallback: ORM
        logger.error(
            f'[BULK_DELETE][SQL_FAST][ERROR] user_id={request.user.id} ids={clean_ids} error={e}',
            exc_info=True
        )
        deleted_count, _ = base_qs.delete()
        logger.info(
            f'[BULK_DELETE][ORM_FALLBACK] Eliminadas {deleted_count} encuestas para user_id={request.user.id}. IDs={clean_ids}'
        )

    # Respuesta AJAX (la que usa tu JS de selección múltiple)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'deleted': deleted_count,
            'deleted_ids': ordered_ids,
            'ordered_by_size': using_annotation,
            'used_fast_path': used_fast_path,
        })

    # Respuesta normal (form POST)
    if used_fast_path:
        messages.success(
            request,
            f'Se eliminaron {deleted_count} encuestas. '
            'Las encuestas más pequeñas se eliminaron primero y las más grandes pueden haber tardado un poco más.'
        )
    else:
        messages.warning(
            request,
            f'Se eliminaron {deleted_count} encuestas usando el método estándar. '
            'Si notas que tarda demasiado con encuestas muy grandes, revisa los logs para más detalles.'
        )

    return redirect('surveys:list')



class SurveyListView(LoginRequiredMixin, EncuestaQuerysetMixin, ListView):
    """List of surveys for the current user."""
    model = Survey
    template_name = 'surveys/list.html'
    context_object_name = 'surveys'
    paginate_by = 12

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.filter(author=self.request.user)
        try:
            qs = qs.annotate(
                total_responses=Count('responses', distinct=True),
                total_questions=Count('questions', distinct=True),
            )
        except FieldError:
            try:
                qs = qs.annotate(
                    total_responses=Count('surveyresponse', distinct=True),
                    total_questions=Count('questions', distinct=True),
                )
            except FieldError:
                pass
        try:
            qs = qs.order_by('-created_at')
        except FieldError:
            qs = qs.order_by('-id')
        return qs



class SurveyDetailView(LoginRequiredMixin, OwnerRequiredMixin, DetailView):
    """Survey detail view (creator only)."""
    model = Survey
    template_name = 'surveys/detail.html'
    context_object_name = 'survey'

    def get_queryset(self):
        return super().get_queryset().prefetch_related(
            Prefetch(
                'questions',
                queryset=Question.objects.order_by('order').prefetch_related(
                    Prefetch('options', queryset=AnswerOption.objects.order_by('order'))
                )
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        survey = context.get('survey') or self.object
        base_url = getattr(settings, 'PUBLIC_BASE_URL', '').strip()
        if base_url:
            base_url = base_url.rstrip('/')
        else:
            base_url = self.request.build_absolute_uri('/').rstrip('/')
            host = self.request.get_host().split(':')[0]
            port = self.request.get_port() or '80'
            lan_ip = getattr(settings, 'LOCAL_LAN_IP', '')
            if host in ('127.0.0.1', 'localhost') and lan_ip:
                scheme = 'http'
                base_url = f"{scheme}://{lan_ip}:{port}"
        respond_path = reverse('surveys:respond', args=[survey.pk])
        context['respond_absolute_url'] = f"{base_url}{respond_path}"
        return context



class SurveyCreateView(LoginRequiredMixin, CreateView):
    """View to create a new survey."""
    model = Survey
    template_name = 'surveys/survey_create.html'
    fields = ['title', 'description', 'category']  # Removido 'status', siempre será draft
    success_url = reverse_lazy('surveys:list')

    def post(self, request, *args, **kwargs):
        """Handle both form POST and JSON API POST."""
        content_type = request.content_type or ''
        
        if 'application/json' in content_type:
            try:
                data = json.loads(request.body)
                
                # Crear la encuesta (siempre en borrador para encuestas web)
                survey = Survey.objects.create(
                    title=data.get('title', 'Sin título'),
                    description=data.get('description', ''),
                    status='draft',  # Siempre empieza en borrador
                    category=data.get('category', 'general'),
                    author=request.user,
                    is_imported=False  # Marca explícita de encuesta manual
                )
                
                # Crear las preguntas
                questions_data = data.get('questions', [])
                for idx, q_data in enumerate(questions_data):
                    question = Question.objects.create(
                        survey=survey,
                        text=q_data.get('text', ''),
                        type=q_data.get('type', 'text'),
                        order=idx + 1,
                        is_required=q_data.get('required', True)
                    )
                    
                    # Crear opciones de respuesta si aplica
                    options = q_data.get('options', [])
                    for opt_idx, opt_text in enumerate(options):
                        if opt_text:
                            AnswerOption.objects.create(
                                question=question,
                                text=opt_text,
                                order=opt_idx + 1
                            )
                
                log_user_action(
                    'create_survey',
                    success=True,
                    user_id=request.user.id,
                    survey_title=survey.title,
                    category=survey.category
                )
                
                try:
                    cache.delete(f"dashboard_data_user_{request.user.id}")
                    cache.delete(f"survey_count_user_{request.user.id}")
                except Exception:
                    pass
                
                return JsonResponse({
                    'success': True,
                    'survey_id': survey.id,
                    'redirect_url': f'/surveys/{survey.id}/'
                })
                
            except json.JSONDecodeError:
                return JsonResponse({'success': False, 'error': 'JSON inválido'}, status=400)
            except Exception as e:
                logger.error(f"[CREATE_SURVEY][ERROR] user_id={request.user.id} error={e}", exc_info=True)
                return JsonResponse({'success': False, 'error': str(e)}, status=500)
        
        # Formulario HTML estándar
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.author = self.request.user
        form.instance.status = 'draft'  # Forzar estado draft en creación por formulario HTML
        log_user_action(
            'create_survey',
            success=True,
            user_id=self.request.user.id,
            survey_title=form.instance.title,
            category=form.instance.category
        )
        try:
            cache.delete(f"dashboard_data_user_{self.request.user.id}")
            cache.delete(f"survey_count_user_{self.request.user.id}")
        except Exception:
            pass
        return super().form_valid(form)



class SurveyUpdateView(LoginRequiredMixin, OwnerRequiredMixin, UpdateView):
    """View to update a survey (creator only)."""
    model = Survey
    fields = ['title', 'description', 'status']
    template_name = 'surveys/form.html'
    success_url = reverse_lazy('surveys:list')



class SurveyDeleteView(LoginRequiredMixin, OwnerRequiredMixin, DeleteView):
    """View to delete a survey (creator only)."""
    model = Survey
    template_name = 'surveys/confirm_delete.html'
    success_url = reverse_lazy('surveys:list')

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        sid = self.object.id
        logger.info(
            "[DEBUG_DELETE_VIEW] Entrando a delete() para survey_id=%s user_id=%s",
            sid,
            request.user.id,
        )
        response = super().delete(request, *args, **kwargs)
        messages.success(request, f"La encuesta {sid} se eliminó correctamente.")
        logger.info("[DELETE][VIEW] Survey %s deleted via DeleteView", sid)
        return response
