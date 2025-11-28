from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
# --- Bulk delete surveys ---
@login_required
@require_POST
def bulk_delete_surveys_view(request):
    """Eliminación bulk ultra-rápida usando SQL crudo."""
    from django.core.cache import cache
    from surveys.signals import disable_signals, enable_signals
    from django.db import connection
    survey_ids = request.POST.getlist('survey_ids')
    if not survey_ids:
        messages.error(request, 'No se seleccionaron encuestas para eliminar.')
        return redirect('surveys:list')
    # Validar propiedad y sanitizar IDs
    try:
        clean_ids = [int(sid) for sid in survey_ids]
    except ValueError:
        messages.error(request, 'IDs inválidos.')
        return redirect('surveys:list')
    # CRÍTICO: deshabilitar signals ANTES de cualquier ORM query
    disable_signals()
    # Verificar que pertenecen al usuario
    owned_ids = list(Survey.objects.filter(
        id__in=clean_ids,
        author=request.user
    ).values_list('id', flat=True))
    if not owned_ids:
        enable_signals()  # Re-habilitar antes de return
        messages.error(request, 'No tienes permisos para eliminar las encuestas seleccionadas.')
        return redirect('surveys:list')
    count = len(owned_ids)
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # Usar PostgreSQL ANY() para pasar array de forma segura
                # 1. QuestionResponse
                cursor.execute("""
                    DELETE FROM surveys_questionresponse 
                    WHERE survey_response_id IN (
                        SELECT id FROM surveys_surveyresponse 
                        WHERE survey_id = ANY(%s)
                    )
                """, [owned_ids])
                # 2. SurveyResponse
                cursor.execute("""
                    DELETE FROM surveys_surveyresponse 
                    WHERE survey_id = ANY(%s)
                """, [owned_ids])
                # 3. AnswerOption
                cursor.execute("""
                    DELETE FROM surveys_answeroption 
                    WHERE question_id IN (
                        SELECT id FROM surveys_question 
                        WHERE survey_id = ANY(%s)
                    )
                """, [owned_ids])
                # 4. Question
                cursor.execute("""
                    DELETE FROM surveys_question 
                    WHERE survey_id = ANY(%s)
                """, [owned_ids])
                # 5. Survey
                cursor.execute("""
                    DELETE FROM surveys_survey 
                    WHERE id = ANY(%s)
                """, [owned_ids])
    except Exception as e:
        logger.error(f"Error en bulk delete: {e}")
        messages.error(request, f"Error eliminando encuestas.")
        return redirect('surveys:list')
    finally:
        enable_signals()
    # Invalidar caché
    cache.delete(f"dashboard_data_user_{request.user.id}")
    # Mensaje de éxito
    if count == 1:
        messages.success(request, 'Se eliminó 1 encuesta correctamente.')
    else:
        messages.success(request, f'Se eliminaron {count} encuestas correctamente.')
    return redirect('surveys:list')
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, CreateView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction, connection
from core.mixins import OwnerRequiredMixin, EncuestaQuerysetMixin
from surveys.models import Survey
from core.utils.logging_utils import StructuredLogger, log_user_action

logger = StructuredLogger('surveys')

class EncuestaListView(LoginRequiredMixin, EncuestaQuerysetMixin, ListView):
    """Vista lista de encuestas del usuario actual."""
    model = Survey
    template_name = 'surveys/list.html'
    context_object_name = 'surveys'

class EncuestaDetailView(LoginRequiredMixin, OwnerRequiredMixin, DetailView):
    """Vista detalle de encuesta (solo creador)."""
    model = Survey
    template_name = 'surveys/detail.html'
    context_object_name = 'survey'

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
        from django.core.cache import cache
        from surveys.signals import disable_signals, enable_signals
        disable_signals()
        survey = self.get_object()
        survey_id = survey.id
        author_id = survey.author.id if survey.author else None
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("""
                        DELETE FROM surveys_questionresponse 
                        WHERE survey_response_id IN (
                            SELECT id FROM surveys_surveyresponse WHERE survey_id = %s
                        )
                    """, [survey_id])
                    cursor.execute("""
                        DELETE FROM surveys_surveyresponse WHERE survey_id = %s
                    """, [survey_id])
                    cursor.execute("""
                        DELETE FROM surveys_answeroption 
                        WHERE question_id IN (
                            SELECT id FROM surveys_question WHERE survey_id = %s
                        )
                    """, [survey_id])
                    cursor.execute("""
                        DELETE FROM surveys_question WHERE survey_id = %s
                    """, [survey_id])
                    cursor.execute("""
                        DELETE FROM surveys_survey WHERE id = %s
                    """, [survey_id])
        except Exception as e:
            logger.error(f"Error eliminando encuesta {survey_id}: {e}")
            messages.error(request, "Error al eliminar la encuesta.")
            return redirect(self.success_url)
        finally:
            enable_signals()
        if author_id:
            cache.delete(f"dashboard_data_user_{author_id}")
            try:
                cache.delete_pattern(f"survey_*{survey_id}*")
            except:
                pass
        messages.success(request, 'Encuesta eliminada correctamente.')
        return redirect(self.success_url)
