
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, CreateView
from django.urls import reverse, reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.core.cache import cache
from django.db.models import Count, Prefetch
from django.core.exceptions import FieldError, ValidationError
from django.http import JsonResponse
from django.db import connection
from django.conf import settings
from django_ratelimit.decorators import ratelimit

import json

from core.mixins import OwnerRequiredMixin, EncuestaQuerysetMixin
from surveys.models import Survey, Question, AnswerOption
from core.utils.logging_utils import StructuredLogger, log_user_action
import time

@login_required
@require_GET
def survey_list_count(request):
    """
    Retorna el número de encuestas del usuario actual (para confirmar borrado).
    """
    count = Survey.objects.filter(owner=request.user).count()
    return JsonResponse({"count": count})

logger = StructuredLogger('surveys')


def legacy_survey_redirect_view(request, pk, legacy_path=None):
    """Redirect old integer-based URLs to the new public_id versions."""
    survey = get_object_or_404(Survey, pk=pk)
    base = reverse('surveys:detail', args=[survey.public_id])
    if legacy_path:
        cleaned = legacy_path.strip('/')
        if cleaned:
            base = f"{base.rstrip('/')}/{cleaned}/"
    return redirect(base)


# Nota: La función _fast_delete_surveys se movió a surveys/tasks.py
# para ser ejecutada de forma asíncrona con Celery


@login_required
@require_GET
def delete_task_status(request, task_id):
    """
    Consultar el estado de una tarea de eliminación Celery.
    """
    from celery.result import AsyncResult
    from celery import current_app
    
    result = AsyncResult(task_id)
    
    response_data = {
        'task_id': task_id,
        'status': result.state,
        'ready': result.ready(),
    }
    
    # Verificar si Celery está disponible (verificación no bloqueante)
    try:
        # Intentar ping a los workers (más confiable que active() en Windows)
        inspect = current_app.control.inspect(timeout=1.0)
        ping_result = inspect.ping()
        
        if ping_result:
            # Hay al menos un worker respondiendo
            response_data['celery_available'] = True
        else:
            # No respondieron workers, pero puede ser timeout
            # No bloqueamos la UI, solo advertimos
            response_data['celery_available'] = False
            # Solo mostrar error si la tarea está realmente pendiente por mucho tiempo
            if result.state == 'PENDING':
                response_data['warning'] = 'No se detectaron workers activos. Verifica que Celery esté corriendo.'
    except Exception as e:
        logger.warning(f"[DELETE_TASK_STATUS] Error verificando workers: {e}")
        # No bloqueamos, asumimos que el worker puede estar corriendo
        response_data['celery_available'] = True  # Asumir disponible para no bloquear UI
    
    if result.ready():
        if result.successful():
            response_data['result'] = result.result
            # La tarea devuelve 'deleted', no 'deleted_count'
            response_data['deleted_count'] = result.result.get('deleted', 0) if isinstance(result.result, dict) else 0
        else:
            response_data['error'] = str(result.info)
    else:
        # Tarea aún en progreso o pendiente
        if result.state == 'PENDING':
            # La tarea está pendiente - puede ser normal si acaba de enviarse
            # Ya agregamos una advertencia arriba si no detectamos workers
            pass
        elif hasattr(result.info, 'get'):
            response_data['progress'] = result.info.get('progress', 0)
    
    return JsonResponse(response_data)


# --- Bulk delete surveys ---
@login_required
@require_POST
@ratelimit(key="user", rate="50/h", method="POST", block=True)
def bulk_delete_surveys_view(request):
    """
    Eliminación masiva usando Celery para procesamiento en background.
    TODO EL BORRADO SE HACE EN CELERY - EL SERVIDOR RESPONDE EN < 200ms.
    Crea una tarea asíncrona y retorna el job_id para polling.
    """
    from surveys.tasks import delete_surveys_task
    
    survey_ids = request.POST.getlist('survey_ids')

    if not survey_ids:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse(
                {'success': False, 'error': 'No se seleccionaron encuestas para eliminar.'},
                status=400
            )
        messages.error(request, 'No se seleccionaron encuestas para eliminar.')
        return redirect('surveys:list')

    # Normalizar IDs
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

    # Verificar permisos (solo validación, no borrado)
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

    # 🚀 Intentar lanzar tarea CELERY (trabajo pesado en background)
    task_result = None
    try:
        task_result = delete_surveys_task.delay(clean_ids, request.user.id)
        logger.info(
            f'[BULK_DELETE][CELERY] Tarea lanzada task_id={task_result.id} user_id={request.user.id} count={len(clean_ids)}'
        )
    except Exception as e:
        logger.warning(f"[BULK_DELETE][CELERY_UNAVAILABLE] Fallback a borrado síncrono: {e}")
    
    # Si Celery no está disponible, borrar de forma síncrona para no dejar la UI inconsistente
    if task_result is None:
        try:
            from django.db import transaction
            with transaction.atomic():
                deleted_count, _ = Survey.objects.filter(id__in=clean_ids, author=request.user).delete()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'deleted': deleted_count,
                    'message': f'Se eliminaron {deleted_count} encuesta(s).',
                })
            messages.success(request, f'Se eliminaron {deleted_count} encuesta(s).')
            return redirect('surveys:list')
        except Exception as e:
            logger.error(f"[BULK_DELETE][SYNC_ERROR] Error en borrado síncrono: {e}")
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': 'No se pudo eliminar encuestas. Inténtalo de nuevo.',
                }, status=500)
            messages.error(request, 'No se pudo eliminar encuestas. Inténtalo de nuevo.')
            return redirect('surveys:list')

    # Respuesta AJAX (< 200ms)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'task_id': task_result.id,
            'total_surveys': len(clean_ids),
            'message': f'Procesando eliminación de {len(clean_ids)} encuesta(s)...'
        })

    # Respuesta normal (< 200ms)
    messages.success(
        request,
        f'Procesando eliminación de {len(clean_ids)} encuesta(s). Esto puede tardar unos momentos.'
    )
    return redirect('surveys:list')



class SurveyListView(LoginRequiredMixin, EncuestaQuerysetMixin, ListView):
    """List of surveys for the current user."""
    model = Survey
    template_name = 'surveys/crud/list.html'
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
    template_name = 'surveys/crud/detail.html'
    context_object_name = 'survey'
    slug_field = 'public_id'
    slug_url_kwarg = 'public_id'

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
            # Nota: Deshabilitamos la conversión automática de 127.0.0.1 a LAN_IP
            # para permitir desarrollo local. Si quieres usar LAN_IP, configura PUBLIC_BASE_URL.
            # host = self.request.get_host().split(':')[0]
            # port = self.request.get_port() or '80'
            # lan_ip = getattr(settings, 'LOCAL_LAN_IP', '')
            # if host in ('127.0.0.1', 'localhost') and lan_ip:
            #     scheme = 'http'
            #     base_url = f"{scheme}://{lan_ip}:{port}"
        respond_path = reverse('surveys:respond', args=[survey.public_id])
        context['respond_absolute_url'] = f"{base_url}{respond_path}"
        return context



class SurveyCreateView(LoginRequiredMixin, CreateView):
    """View to create a new survey."""
    model = Survey
    template_name = 'surveys/forms/survey_create.html'
    fields = ['title', 'description', 'category']  # Removido 'status', siempre será draft
    success_url = reverse_lazy('surveys:list')

    def post(self, request, *args, **kwargs):
        """Handle both form POST and JSON API POST."""
        content_type = request.content_type or ''
        
        if 'application/json' in content_type:
            try:
                data = json.loads(request.body)

                # Compatibilidad con payloads antiguos (surveyInfo/titulo/descripcion)
                legacy_info = data.get('surveyInfo') or {}
                title = (
                    data.get('title')
                    or legacy_info.get('title')
                    or legacy_info.get('titulo')
                    or 'Sin título'
                )
                description = (
                    data.get('description')
                    or legacy_info.get('description')
                    or legacy_info.get('descripcion')
                    or ''
                )
                category = (
                    data.get('category')
                    or legacy_info.get('category')
                    or legacy_info.get('categoria')
                    or 'general'
                )

                # Crear la encuesta (siempre en borrador para encuestas web)
                survey = Survey.objects.create(
                    title=title,
                    description=description,
                    status='draft',  # Siempre empieza en borrador
                    category=category,
                    author=request.user,
                    is_imported=False  # Marca explícita de encuesta manual
                )
                
                # Crear las preguntas
                questions_data = data.get('questions', [])
                for idx, q_data in enumerate(questions_data):
                    question_text = (
                        q_data.get('text')
                        or q_data.get('title')
                        or q_data.get('titulo')
                        or ''
                    )
                    question_type = q_data.get('type') or q_data.get('tipo') or 'text'
                    question = Question.objects.create(
                        survey=survey,
                        text=question_text,
                        type=question_type,
                        order=idx + 1,
                        is_required=q_data.get('required', True)
                    )
                    
                    # Crear opciones de respuesta si aplica
                    options = q_data.get('options') or q_data.get('opciones') or []
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
                    'redirect_url': reverse('surveys:detail', args=[survey.public_id])
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
    template_name = 'surveys/forms/form.html'
    success_url = reverse_lazy('surveys:list')
    slug_field = 'public_id'
    slug_url_kwarg = 'public_id'

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if getattr(self, 'object', None) and self.object.is_imported:
            form.fields.pop('status', None)
        return form

    def form_valid(self, form):
        survey = form.instance
        original_status = Survey.objects.only('status').get(pk=survey.pk).status
        new_status = form.cleaned_data.get('status', original_status)

        if survey.is_imported:
            form.instance.status = original_status
        else:
            try:
                survey.validate_status_transition(new_status, from_status=original_status)
            except ValidationError as exc:
                form.add_error('status', exc)
                form.instance.status = original_status
                return self.form_invalid(form)

        return super().form_valid(form)



# Modifica SurveyDeleteView en surveys/views/crud_views.py

class SurveyDeleteView(LoginRequiredMixin, OwnerRequiredMixin, DeleteView):
    """
    Vista para eliminar una encuesta individual (solo el creador).
    """
    model = Survey
    template_name = 'surveys/crud/confirm_delete.html'
    success_url = reverse_lazy('surveys:list')
    slug_field = 'public_id'
    slug_url_kwarg = 'public_id'

    def delete(self, request, *args, **kwargs):
        """
        Sobrescribe delete para usar Celery y soportar AJAX.
        """
        from surveys.tasks import delete_surveys_task
        
        self.object = self.get_object()
        survey_id = self.object.id
        survey_title = self.object.title
        
        logger.info(f"[DELETE] Iniciando borrado asíncrono survey_id={survey_id}")
        
        # 🚀 LANZAR TAREA CELERY
        task_result = delete_surveys_task.delay([survey_id], request.user.id)
        
        # --- NUEVO: RESPUESTA JSON PARA AJAX ---
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'task_id': task_result.id,
                'message': f"Eliminando '{survey_title}'..."
            })
        
        # Fallback para peticiones normales (no recomendada para grandes volúmenes)
        messages.success(request, f"Procesando eliminación de '{survey_title}'...")
        return redirect(self.success_url)