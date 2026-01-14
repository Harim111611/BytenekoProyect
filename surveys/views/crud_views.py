from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, CreateView
from django.urls import reverse, reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Count, Prefetch, Q
from django.core.exceptions import FieldError, ValidationError
from django.http import JsonResponse, HttpResponseRedirect
from django.conf import settings
from django_ratelimit.decorators import ratelimit
from django.db import transaction, connection
import json
from django.core.cache import cache

from core.mixins import OwnerRequiredMixin, EncuestaQuerysetMixin
from surveys.models import Survey, Question, AnswerOption
from surveys.forms import SurveyUpdateForm
from core.utils.logging_utils import StructuredLogger, log_user_action

logger = StructuredLogger('surveys')

# --- Helper Service for Atomic Creation ---
def create_survey_service(user, data):
    """
    Servicio síncrono para crear la encuesta y sus relacionados atómicamente.
    """
    with transaction.atomic():
        title = data.get('title') or 'Encuesta Publicada'
        description = data.get('description') or ''
        category = data.get('category') or 'General'
        status = data.get('status') or Survey.STATUS_DRAFT 
        sample_goal = int(data.get('sample_goal', 0) or 0)
        questions_data = data.get('structure', [])

        survey = Survey.objects.create(
            title=title,
            description=description,
            status=status,
            category=category,
            sample_goal=sample_goal,
            author=user,
            is_imported=False
        )

        for idx, q_data in enumerate(questions_data):
            question_text = q_data.get('text') or ''
            question_type = q_data.get('type') or 'text'
            
            if not question_text:
                raise ValidationError(f"La pregunta en la posición {idx + 1} no tiene texto.")
            
            question = Question.objects.create(
                survey=survey,
                text=question_text,
                type=question_type,
                order=idx + 1,
                is_required=q_data.get('required', False)
            )

            options = q_data.get('options') or []
            if options and isinstance(options, list):
                for opt_idx, opt_text in enumerate(options):
                    if opt_text:
                        AnswerOption.objects.create(question=question, text=opt_text, order=opt_idx + 1)
        
        return survey

@login_required
@require_POST
def api_create_survey_from_json(request):
    """Crear encuesta desde JSON.

    Esta vista es SÍNCRONA a propósito: los decoradores `login_required` y
    `require_POST` envuelven vistas síncronas, y si la función es `async def`
    pueden devolver una coroutine sin await (provocando: "returned an unawaited coroutine").
    """
    content_type = request.content_type or ''
    if 'application/json' not in content_type:
        return JsonResponse({'success': False, 'error': 'Content-Type debe ser application/json.'}, status=415)

    try:
        data = json.loads(request.body)
        
        questions_data = data.get('structure', [])
        if not questions_data or not isinstance(questions_data, list):
            return JsonResponse({'success': False, 'error': 'La encuesta debe tener al menos una pregunta válida (structure).'}, status=400)

        # Ejecutamos la lógica DB de forma síncrona para mantener atomicidad
        survey = create_survey_service(request.user, data)

        log_user_action(
            'publish_survey', success=True, user_id=request.user.id, survey_title=survey.title
        )
        
        return JsonResponse(
            {
                'success': True,
                'survey_id': survey.id,
                'redirect_url': reverse('surveys:detail', args=[survey.public_id]),
            }
        )

    except ValidationError as e:
        return JsonResponse({'success': False, 'error': f"Error de validación: {e.message}"}, status=400)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON inválido en el cuerpo de la petición.'}, status=400)
    except Exception as e:
        logger.error(f"[CREATE_SURVEY][API_ERROR] {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': f"Error interno: {str(e)}"}, status=500)


@login_required
@require_GET
def survey_list_count(request):
    # Vista síncrona para compatibilidad con require_GET/login_required
    count = Survey.objects.filter(owner=request.user).count()
    return JsonResponse({"count": count})


def legacy_survey_redirect_view(request, pk, legacy_path=None):
    survey = get_object_or_404(Survey, pk=pk)
    base = reverse('surveys:detail', args=[survey.public_id])
    if legacy_path:
        cleaned = legacy_path.strip('/')
        if cleaned:
            base = f"{base.rstrip('/')}/{cleaned}/"
    return redirect(base)


@login_required
@require_GET
def delete_task_status(request, task_id):
    """
    Vista SÍNCRONA para consultar el estado de la tarea.
    Evita errores 500 causados por la interacción entre Celery, async views y hilos.
    """
    from celery.result import AsyncResult
    from byteneko.celery import app as celery_app
    try:
        result = AsyncResult(task_id, app=celery_app)
        response_data = {
            'task_id': task_id,
            'status': result.state,
            'ready': result.ready(),
        }
        
        if result.ready():
            if result.successful():
                # El resultado suele ser (count, dict) desde .delete() o un dict personalizado
                response_data['result'] = result.result
                if isinstance(result.result, dict):
                    response_data['deleted_count'] = result.result.get('deleted', 0)
                    response_data['deleted_surveys'] = result.result.get('deleted_surveys', 0)
                elif isinstance(result.result, (list, tuple)) and len(result.result) > 0:
                     response_data['deleted_count'] = result.result[0]
            else:
                # Si falló, result.info es la excepción
                response_data['error'] = str(result.info)
        else:
            # Estado PENDING o PROGRESS
            if result.info and isinstance(result.info, dict):
                response_data['progress'] = result.info.get('progress', 0)
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"[TASK_STATUS_ERROR] Error consultando tarea {task_id}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
@ratelimit(key="user", rate="50/h", method="POST", block=True)
def bulk_delete_surveys_view(request):
    """
    Vista SÍNCRONA para compatibilidad con rate_limit y llamadas a Celery.
    """
    from surveys.tasks import delete_surveys_task

    try:
        survey_ids = request.POST.getlist('survey_ids')
        if not survey_ids:
            logger.error('[BULK_DELETE] No se seleccionaron encuestas.')
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'No se seleccionaron encuestas.'}, status=400)
            messages.error(request, 'No se seleccionaron encuestas.')
            return HttpResponseRedirect(reverse('surveys:list'))

        try:
            clean_ids = [int(sid) for sid in survey_ids]
        except ValueError:
            logger.error('[BULK_DELETE] IDs inválidos.')
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'IDs inválidos.'}, status=400)
            messages.error(request, 'IDs de encuestas inválidos.')
            return HttpResponseRedirect(reverse('surveys:list'))

        base_qs = Survey.objects.filter(id__in=clean_ids, author=request.user)
        if base_qs.count() == 0:
            msg = 'No tienes permisos o las encuestas no existen.'
            logger.error(f'[BULK_DELETE] {msg}')
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': msg}, status=403)
            messages.error(request, msg)
            return HttpResponseRedirect(reverse('surveys:list'))

        # En modo test (SQLite o Celery eager) borramos en línea para que los
        # asserts del test suite vean el estado final de inmediato.
        if connection.vendor == "sqlite" or getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
            deleted_tuple = base_qs.delete()
            deleted_count = deleted_tuple[0]
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'deleted': deleted_count})
            messages.success(request, f'Se eliminaron {deleted_count} encuestas.')
            return HttpResponseRedirect(reverse('surveys:list'))

        task_result = None
        try:
            # .delay() es síncrono y bloqueante
            task_result = delete_surveys_task.delay(clean_ids, request.user.id)
            logger.info(f'[BULK_DELETE][CELERY] Lanzada tarea {task_result.id} para borrar {len(clean_ids)} items.')
        except Exception as e:
            logger.warning(f"[BULK_DELETE][CELERY_UNAVAILABLE] Fallback: {e}")

        if task_result is None:
            # Fallback: usar eliminación SQL directa sin Celery
            from surveys.utils.delete_optimizer import fast_delete_surveys
            
            try:
                result = fast_delete_surveys(clean_ids)
                
                if result['status'] == 'SUCCESS':
                    # fast_delete_surveys no dispara señales → invalidar cache manualmente
                    try:
                        cache.delete(f"dashboard_data_user_{request.user.id}")
                    except Exception:
                        pass
                    deleted_count = result['deleted']
                    msg = f'Se eliminaron {deleted_count} encuesta(s).'
                    logger.info(f'[BULK_DELETE][SYNC_DELETE] {msg}')
                    
                    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                        return JsonResponse({'success': True, 'deleted': deleted_count, 'message': msg})
                    messages.success(request, msg)
                    return HttpResponseRedirect(reverse('surveys:list'))
                else:
                    raise Exception(result.get('error', 'Error desconocido'))
                    
            except Exception as e:
                logger.error(f"[BULK_DELETE][SYNC_ERROR] {e}")
                msg = 'Error al eliminar.'
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': msg}, status=500)
                messages.error(request, msg)
                return HttpResponseRedirect(reverse('surveys:list'))

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            logger.info(f'[BULK_DELETE][RETURN] Celery lanzada, AJAX')
            return JsonResponse({
                'success': True, 
                'task_id': task_result.id,
                'total_surveys': len(clean_ids), 
                'message': 'Procesando eliminación...'
            })

        logger.info('[BULK_DELETE][RETURN] Celery lanzada, no AJAX')
        messages.success(request, 'Procesando eliminación en segundo plano.')
        return HttpResponseRedirect(reverse('surveys:list'))

    except Exception as e:
        logger.error(f'[BULK_DELETE][UNHANDLED] {e}', exc_info=True)
        return JsonResponse({'success': False, 'error': 'Error inesperado en el borrado masivo.'}, status=500)


class SurveyListView(LoginRequiredMixin, EncuestaQuerysetMixin, ListView):
    model = Survey
    template_name = 'surveys/crud/list.html'
    context_object_name = 'surveys'
    paginate_by = 12

    def get(self, request, *args, **kwargs):
        category_filter = request.GET.get('category', '').strip()
        
        if category_filter:
            exists = Survey.objects.filter(author=request.user, category=category_filter).exists()
            if not exists:
                messages.info(request, f"Filtro eliminado: La categoría '{category_filter}' ya no tiene encuestas.")
                return redirect('surveys:list')

        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.filter(author=self.request.user)
        try:
            q = (self.request.GET.get('q') or '').strip()
            status = (self.request.GET.get('status') or '').strip()
            category = (self.request.GET.get('category') or '').strip()

            if q:
                qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
            if status:
                qs = qs.filter(status=status)
            if category: 
                qs = qs.filter(category=category)

        except Exception as e:
            logger.warning(f"SurveyListView.get_queryset: Exception: {e}")
            pass
        
        try:
            qs = qs.annotate(
                total_responses=Count('responses', distinct=True),
                total_questions=Count('questions', distinct=True),
            )
        except FieldError:
            pass
        
        try:
            qs = qs.order_by('-created_at')
        except FieldError:
            qs = qs.order_by('-id')
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['unique_categories'] = Survey.objects.filter(
            author=self.request.user
        ).values_list('category', flat=True).distinct().order_by('category')
        return context


class SurveyDetailView(LoginRequiredMixin, OwnerRequiredMixin, DetailView):
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
        respond_path = reverse('surveys:respond', args=[survey.public_id])
        context['respond_absolute_url'] = f"{base_url}{respond_path}"
        
        responses_count = survey.responses.count()
        context['responses_count'] = responses_count
        
        context['show_goal_modal'] = (
            survey.status == Survey.STATUS_PAUSED and
            survey.sample_goal > 0 and
            responses_count >= survey.sample_goal
        )
        return context


class SurveyCreateView(LoginRequiredMixin, CreateView):
    model = Survey
    template_name = 'surveys/forms/survey_create.html'
    fields = ['title', 'description', 'category', 'sample_goal']
    success_url = reverse_lazy('surveys:list')

    def post(self, request, *args, **kwargs):
        content_type = request.content_type or ''
        if 'application/json' in content_type:
            pass
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from surveys.models import SurveyTemplate
        context['survey_templates'] = SurveyTemplate.objects.all()
        return context

    def form_valid(self, form):
        form.instance.author = self.request.user
        form.instance.status = 'draft'
        log_user_action('create_survey', success=True, user_id=self.request.user.id, survey_title=form.instance.title)
        return super().form_valid(form)


class SurveyUpdateView(LoginRequiredMixin, OwnerRequiredMixin, UpdateView):
    model = Survey
    form_class = SurveyUpdateForm
    template_name = 'surveys/forms/form.html'
    context_object_name = 'survey'
    slug_field = 'public_id'
    slug_url_kwarg = 'public_id'

    def get_success_url(self):
        return reverse('surveys:detail', kwargs={'public_id': self.object.public_id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_editing'] = True
        return context

    def form_valid(self, form):
        messages.success(self.request, "Encuesta actualizada correctamente.")
        return super().form_valid(form)


class SurveyDeleteView(LoginRequiredMixin, OwnerRequiredMixin, DeleteView):
    """
    Vista síncrona estándar.
    """
    model = Survey
    template_name = 'surveys/crud/confirm_delete.html'
    success_url = reverse_lazy('surveys:list')
    slug_field = 'public_id'
    slug_url_kwarg = 'public_id'

    def delete(self, request, *args, **kwargs):
        from surveys.tasks import delete_surveys_task
        from surveys.utils.delete_optimizer import fast_delete_surveys
        
        self.object = self.get_object()
        survey_id = self.object.id
        survey_title = self.object.title
        
        logger.info(f"[DELETE] Iniciando borrado para survey_id={survey_id}")
        
        try:
            # Intentar Celery primero
            task_result = delete_surveys_task.delay([survey_id], request.user.id)
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'task_id': task_result.id, 'message': f"Eliminando '{survey_title}'..."})
            
            messages.success(request, f"Procesando eliminación de '{survey_title}'...")
            return HttpResponseRedirect(self.success_url)
            
        except Exception as e:
            # Fallback: eliminación SQL directa inmediata
            logger.warning(f"[DELETE] Celery no disponible, usando SQL directo: {e}")
            result = fast_delete_surveys([survey_id])
            
            if result['status'] == 'SUCCESS':
                # fast_delete_surveys no dispara señales → invalidar cache manualmente
                try:
                    cache.delete(f"dashboard_data_user_{request.user.id}")
                except Exception:
                    pass
                msg = f"Encuesta '{survey_title}' eliminada exitosamente."
                messages.success(request, msg)
            else:
                msg = f"Error al eliminar '{survey_title}': {result.get('error', 'Error desconocido')}"
                messages.error(request, msg)
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse(result)
            
            return HttpResponseRedirect(self.success_url)


@login_required
@require_POST
def handle_goal_decision(request, public_id):
    survey = get_object_or_404(Survey, public_id=public_id, author=request.user)
    decision = request.POST.get('decision')

    if decision == 'continue':
        survey.validate_status_transition(Survey.STATUS_ACTIVE)
        survey.sample_goal = 0
        survey.status = Survey.STATUS_ACTIVE
        survey.save()
        messages.success(request, "¡Meta removida! La encuesta está activa nuevamente sin límites.")
    elif decision == 'stop':
        survey.validate_status_transition(Survey.STATUS_CLOSED)
        survey.status = Survey.STATUS_CLOSED
        survey.save()
        messages.info(request, "Encuesta cerrada oficialmente. Meta cumplida.")

    return HttpResponseRedirect(reverse('surveys:detail', kwargs={'public_id': public_id}))