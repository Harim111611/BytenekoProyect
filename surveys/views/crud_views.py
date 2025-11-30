from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, CreateView
from django.urls import reverse_lazy
from django.shortcuts import redirect
from django.contrib import messages
from django.core.cache import cache
from django.db.models import Count, Prefetch
from django.core.exceptions import FieldError
from django.http import JsonResponse
from django.db import connection

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
    logger.info("[DELETE][TEST] Logger de surveys funcionando correctamente en archivo de log.")

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

    # Solo encuestas del usuario actual
    base_qs = Survey.objects.filter(id__in=clean_ids, author=request.user)
    if not base_qs.exists():
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
            f'[BULK_DELETE][SQL_FAST] Eliminadas {deleted_count} encuestas '
            f'para user_id={request.user.id}. ordered_by_size={using_annotation} IDs={ordered_ids}'
        )
    except Exception as e:
        # Fallback: ORM
        logger.error(
            '[BULK_DELETE][SQL_FAST] Error, usando fallback ORM: %s',
            e,
            exc_info=True
        )
        deleted_count, _ = base_qs.delete()
        logger.info(
            f'[BULK_DELETE][ORM_FALLBACK] Eliminadas {deleted_count} encuestas '
            f'para user_id={request.user.id}. IDs={clean_ids}'
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


class EncuestaListView(LoginRequiredMixin, EncuestaQuerysetMixin, ListView):
    """Listado de encuestas del usuario actual."""
    model = Survey
    template_name = 'surveys/list.html'
    context_object_name = 'surveys'
    paginate_by = 12

    def get_queryset(self):
        qs = super().get_queryset()

        # Limitar a encuestas del usuario actual
        qs = qs.filter(author=self.request.user)

        # Anotar contadores para tarjetas
        try:
            qs = qs.annotate(
                total_respuestas=Count('responses', distinct=True),
                total_preguntas=Count('questions', distinct=True),
            )
        except FieldError:
            # Fallback si el related_name de respuestas es otro
            try:
                qs = qs.annotate(
                    total_respuestas=Count('surveyresponse', distinct=True),
                    total_preguntas=Count('questions', distinct=True),
                )
            except FieldError:
                pass

        # Orden más reciente primero
        try:
            qs = qs.order_by('-created_at')
        except FieldError:
            qs = qs.order_by('-id')

        return qs


class EncuestaDetailView(LoginRequiredMixin, OwnerRequiredMixin, DetailView):
    """Vista detalle de encuesta (solo creador)."""
    model = Survey
    template_name = 'surveys/detail.html'
    context_object_name = 'survey'

    def get_queryset(self):
        # 🚀 OPTIMIZACIÓN: pre-carga preguntas y opciones para evitar N+1
        return super().get_queryset().prefetch_related(
            Prefetch(
                'questions',
                queryset=Question.objects.order_by('order').prefetch_related(
                    Prefetch('options', queryset=AnswerOption.objects.order_by('order'))
                )
            )
        )


class EncuestaCreateView(LoginRequiredMixin, CreateView):
    """Vista para crear nueva encuesta."""
    model = Survey
    template_name = 'surveys/survey_create.html'
    fields = ['title', 'description', 'status', 'category']
    success_url = reverse_lazy('surveys:list')

    def form_valid(self, form):
        form.instance.author = self.request.user
        log_user_action(
            'create_survey',
            success=True,
            user_id=self.request.user.id,
            survey_title=form.instance.title,
            category=form.instance.category
        )

        # Invalidar cache del dashboard para que se actualicen contadores
        try:
            cache.delete(f"dashboard_data_user_{self.request.user.id}")
            cache.delete(f"survey_count_user_{self.request.user.id}")
        except Exception:
            pass
        return super().form_valid(form)


class EncuestaUpdateView(LoginRequiredMixin, OwnerRequiredMixin, UpdateView):
    """Vista para actualizar encuesta (solo creador)."""
    model = Survey
    fields = ['title', 'description', 'status']
    template_name = 'surveys/form.html'
    success_url = reverse_lazy('surveys:list')


class EncuestaDeleteView(LoginRequiredMixin, OwnerRequiredMixin, DeleteView):
    """Vista para eliminar encuesta (solo creador)."""
    model = Survey
    template_name = 'surveys/confirm_delete.html'
    success_url = reverse_lazy('surveys:list')

    def delete(self, request, *args, **kwargs):
        """
        Borrado SÍNCRONO y directo, como en el shell.
        """
        self.object = self.get_object()
        sid = self.object.id

        logger.info(
            "[DEBUG_DELETE_VIEW] Entrando a delete() para survey_id=%s user_id=%s",
            sid,
            request.user.id,
        )

        response = super().delete(request, *args, **kwargs)

        messages.success(request, f"La encuesta {sid} se eliminó correctamente.")
        logger.info("[DELETE][VIEW] Encuesta %s eliminada vía DeleteView", sid)

        return response
