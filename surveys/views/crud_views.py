from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, CreateView
from django.urls import reverse, reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Count, Prefetch, Q
from django.core.exceptions import FieldError, ValidationError
from django.http import JsonResponse
from django.conf import settings
from django_ratelimit.decorators import ratelimit
from django.db import transaction # Importación esencial
import json

from core.mixins import OwnerRequiredMixin, EncuestaQuerysetMixin
from surveys.models import Survey, Question, AnswerOption
from core.utils.logging_utils import StructuredLogger, log_user_action

logger = StructuredLogger('surveys')

@login_required
@require_POST
@transaction.atomic
def api_create_survey_from_json(request):
    """
    API endpoint para crear un nuevo Survey (encuesta), incluyendo Questions y AnswerOptions,
    desde el payload JSON enviado por el botón "Publicar" en survey_creator.js.
    """
    
    content_type = request.content_type or ''
    if 'application/json' not in content_type:
        return JsonResponse({'success': False, 'error': 'Content-Type debe ser application/json.'}, status=415)

    try:
        data = json.loads(request.body)
        
        # Extracción segura de datos
        title = data.get('title') or 'Encuesta Publicada'
        description = data.get('description') or ''
        category = data.get('category') or 'General'
        status = data.get('status') or Survey.STATUS_ACTIVE 
        sample_goal = int(data.get('sample_goal', 0) or 0)
        
        questions_data = data.get('structure', []) # El JS envía la estructura en 'structure'

        if not questions_data or not isinstance(questions_data, list):
             return JsonResponse({'success': False, 'error': 'La encuesta debe tener al menos una pregunta válida (structure).'}, status=400)
             
        # 1. Crear la Survey
        survey = Survey.objects.create(
            title=title,
            description=description,
            status=status,
            category=category,
            sample_goal=sample_goal,
            author=request.user,
            is_imported=False
        )
        
        # 2. Crear Preguntas y Opciones
        for idx, q_data in enumerate(questions_data):
            question_text = q_data.get('text') or ''
            question_type = q_data.get('type') or 'text'
            
            if not question_text:
                raise ValidationError(f"La pregunta en la posición {idx + 1} no tiene texto.")
            # Asignar siempre un order secuencial, ignorando el recibido
            question = Question.objects.create(
                survey=survey,
                text=question_text,
                type=question_type,
                order=idx + 1,
                is_required=q_data.get('required', False)
            )
            
            # Opciones: El JS ya asegura que options es una lista de strings o []
            options = q_data.get('options') or []
            if options and isinstance(options, list):
                for opt_idx, opt_text in enumerate(options):
                    if opt_text: # Asegurar que la opción no esté vacía
                        AnswerOption.objects.create(question=question, text=opt_text, order=opt_idx + 1)
        
        log_user_action('publish_survey', success=True, user_id=request.user.id, survey_title=survey.title)
        
        return JsonResponse({
            'success': True, 
            'survey_id': survey.id, 
            'redirect_url': reverse('surveys:detail', args=[survey.public_id])
        })
        
    except ValidationError as e:
        # Captura errores de validación, por ejemplo, si la pregunta no tiene texto
        return JsonResponse({'success': False, 'error': f"Error de validación: {e.message}"}, status=400)
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON inválido en el cuerpo de la petición.'}, status=400)
        
    except Exception as e:
        logger.error(f"[CREATE_SURVEY][API_ERROR] {e}", exc_info=True)
        # El rollback de la transacción se maneja automáticamente por el decorador @transaction.atomic
        return JsonResponse({'success': False, 'error': f"Error interno: {str(e)}"}, status=500)


@login_required
@require_GET
def survey_list_count(request):
    """
    Retorna el número de encuestas del usuario actual (para confirmar borrado).
    """
    count = Survey.objects.filter(owner=request.user).count()
    return JsonResponse({"count": count})


def legacy_survey_redirect_view(request, pk, legacy_path=None):
    """Redirect old integer-based URLs to the new public_id versions."""
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
    Consultar el estado de una tarea de eliminación Celery.
    """
    from celery.result import AsyncResult
    # from celery import current_app # Eliminamos el ping para evitar crashes/timeouts
    
    result = AsyncResult(task_id)
    
    response_data = {
        'task_id': task_id,
        'status': result.state,
        'ready': result.ready(),
    }
    
    # Eliminado el check de 'celery_available' con ping() porque es costoso y propenso a errores
    # durante polling frecuente.
    
    if result.ready():
        if result.successful():
            response_data['result'] = result.result
            response_data['deleted_count'] = result.result.get('deleted', 0) if isinstance(result.result, dict) else 0
            # number of surveys requested to delete (user-facing)
            response_data['deleted_surveys'] = result.result.get('deleted_surveys', 0) if isinstance(result.result, dict) else 0
        else:
            response_data['error'] = str(result.info)
    else:
        if hasattr(result.info, 'get'):
            response_data['progress'] = result.info.get('progress', 0)
    
    return JsonResponse(response_data)


@login_required
@require_POST
@ratelimit(key="user", rate="50/h", method="POST", block=True)
def bulk_delete_surveys_view(request):
    """
    Eliminación masiva optimizada.
    Lanza una única tarea de Celery para todos los IDs (Delete WHERE IN).
    """
    from surveys.tasks import delete_surveys_task
    
    survey_ids = request.POST.getlist('survey_ids')

    if not survey_ids:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'No se seleccionaron encuestas.'}, status=400)
        messages.error(request, 'No se seleccionaron encuestas.')
        return redirect('surveys:list')

    try:
        clean_ids = [int(sid) for sid in survey_ids]
    except ValueError:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'IDs inválidos.'}, status=400)
        messages.error(request, 'IDs de encuestas inválidos.')
        return redirect('surveys:list')

    # Validación rápida de permisos (opcional, la tarea también puede verificar, 
    # pero mejor filtrar aquí para no lanzar tareas inútiles)
    base_qs = Survey.objects.filter(id__in=clean_ids, author=request.user)
    count = base_qs.count()
    if count == 0:
        msg = 'No tienes permisos o las encuestas no existen.'
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': msg}, status=403)
        messages.error(request, msg)
        return redirect('surveys:list')

    task_result = None
    try:
        # Lanzamos una única tarea. El SQL 'DELETE WHERE id IN (...)' es muy eficiente
        # y no requiere splitting para este volumen.
        task_result = delete_surveys_task.delay(clean_ids, request.user.id)
        logger.info(f'[BULK_DELETE][CELERY] Lanzada tarea {task_result.id} para borrar {len(clean_ids)} items.')
    except Exception as e:
        logger.warning(f"[BULK_DELETE][CELERY_UNAVAILABLE] Fallback: {e}")

    # Fallback síncrono si Celery falla
    if task_result is None:
        try:
            from django.db import transaction
            with transaction.atomic():
                deleted_count, _ = Survey.objects.filter(id__in=clean_ids, author=request.user).delete()
            
            msg = f'Se eliminaron {len(clean_ids)} encuesta(s).'
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                # Retornamos success directo sin task_id
                return JsonResponse({'success': True, 'deleted': deleted_count, 'message': msg})
            
            messages.success(request, msg)
            return redirect('surveys:list')
        except Exception as e:
            logger.error(f"[BULK_DELETE][SYNC_ERROR] {e}")
            msg = 'Error al eliminar.'
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': msg}, status=500)
            messages.error(request, msg)
            return redirect('surveys:list')

    # Respuesta exitosa para JS con task_id
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True, 
            'task_id': task_result.id,  # CRUCIAL: El JS espera 'task_id', no 'group_id'
            'total_surveys': len(clean_ids), 
            'message': 'Procesando eliminación...'
        })

    messages.success(request, 'Procesando eliminación en segundo plano.')
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
        # Aplicar filtros de búsqueda y estado desde query params
        try:
            q = (self.request.GET.get('q') or '').strip()
            status = (self.request.GET.get('status') or '').strip()
            if q:
                qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
            if status:
                qs = qs.filter(status=status)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"SurveyListView.get_queryset: Exception: {e}")
            # In case of any error, don't break the list
            pass
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
            except FieldError as e:
                import logging
                logging.getLogger(__name__).warning(f"SurveyListView.get_queryset: FieldError: {e}")
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
        
        # --- Lógica de URL ---
        base_url = getattr(settings, 'PUBLIC_BASE_URL', '').strip()
        if base_url:
            base_url = base_url.rstrip('/')
        else:
            base_url = self.request.build_absolute_uri('/').rstrip('/')
        respond_path = reverse('surveys:respond', args=[survey.public_id])
        context['respond_absolute_url'] = f"{base_url}{respond_path}"
        
        # --- Lógica de Meta de Respuestas ---
        responses_count = survey.responses.count()
        context['responses_count'] = responses_count
        
        # Flag para el modal: Si está pausada, tiene meta y la alcanzó
        context['show_goal_modal'] = (
            survey.status == Survey.STATUS_PAUSED and
            survey.sample_goal > 0 and
            responses_count >= survey.sample_goal
        )
        
        return context


class SurveyCreateView(LoginRequiredMixin, CreateView):
    """View to create a new survey."""
    model = Survey
    template_name = 'surveys/forms/survey_create.html'
    fields = ['title', 'description', 'category', 'sample_goal'] # Agregado sample_goal
    success_url = reverse_lazy('surveys:list')

    # El método post original ya no es necesario, ya que api_create_survey_from_json 
    # manejará la creación JSON. Dejamos el post si es necesario para el form HTML.
    def post(self, request, *args, **kwargs):
        """Maneja solo el POST de formulario si el JSON no se hubiera desviado."""
        content_type = request.content_type or ''
        
        # Si el JS falló y la petición llegó aquí como JSON, lo procesamos (fallback/redundancia)
        if 'application/json' in content_type:
            # Esta lógica ya estaba en tu código, pero se recomienda moverla a la API
            # para claridad. Como el JS llama al endpoint /create_survey/, esta ruta 
            # ya no será necesaria para el JSON y funcionará como GET/POST de formulario normal.
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
    """View to update a survey (creator only)."""
    model = Survey
    fields = ['title', 'description', 'status', 'sample_goal'] # Agregado sample_goal
    template_name = 'surveys/forms/form.html'
    success_url = reverse_lazy('surveys:list')
    slug_field = 'public_id'
    slug_url_kwarg = 'public_id'


    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        survey = self.object
        context['survey_questions'] = survey.questions.all()
        context['answer_options'] = AnswerOption.objects.filter(question__survey=survey)
        return context

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
        from surveys.tasks import delete_surveys_task
        self.object = self.get_object()
        survey_id = self.object.id
        survey_title = self.object.title
        logger.info(f"[DELETE] Iniciando borrado asíncrono survey_id={survey_id}")
        task_result = delete_surveys_task.delay([survey_id], request.user.id)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'task_id': task_result.id, 'message': f"Eliminando '{survey_title}'..."})
        messages.success(request, f"Procesando eliminación de '{survey_title}'...")
        return redirect(self.success_url)


# --- NUEVA VISTA PARA GESTIONAR EL MODAL DE META ---
@login_required
@require_POST
def handle_goal_decision(request, public_id):
    """
    Procesa la decisión del usuario cuando se alcanza la meta.
    """
    survey = get_object_or_404(Survey, public_id=public_id, author=request.user)
    decision = request.POST.get('decision') # 'continue' o 'stop'
    
    if decision == 'continue':
        # Opción SÍ: Quitar límite y reactivar
        survey.sample_goal = 0 # 0 = Ilimitado
        survey.status = Survey.STATUS_ACTIVE
        survey.save()
        messages.success(request, "¡Meta removida! La encuesta está activa nuevamente sin límites.")
        
    elif decision == 'stop':
        # Opción NO: Cerrar definitivamente
        survey.status = Survey.STATUS_CLOSED
        survey.save()
        messages.info(request, "Encuesta cerrada oficialmente. Meta cumplida.")
        
    return redirect('surveys:detail', public_id=public_id)