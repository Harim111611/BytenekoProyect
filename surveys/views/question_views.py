# surveys/views/question_views.py
"""
Vistas para operaciones CRUD de preguntas (edición inline desde detail view).
"""
import json
import logging

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_POST
from django.db import transaction

from surveys.models import Survey, Question, AnswerOption
from core.utils.helpers import PermissionHelper

logger = logging.getLogger('surveys')


@login_required
@require_POST
def update_question_view(request, pk):
    """Actualizar una pregunta existente (AJAX)."""
    try:
        question = get_object_or_404(Question.objects.select_related('survey'), pk=pk)
    except Http404:
        logger.warning(f"Intento de actualizar pregunta inexistente: ID {pk} por usuario {request.user.username}")
        return JsonResponse({'success': False, 'error': 'Pregunta no encontrada'}, status=404)
    
    # Verificar permisos (solo el autor puede editar)
    if question.survey.author != request.user:
        logger.warning(f"Usuario {request.user.username} intentó editar pregunta {pk} sin permisos")
        return JsonResponse({'success': False, 'error': 'Sin permisos'}, status=403)
    
    # Validar que la encuesta esté en borrador
    if question.survey.status != 'draft':
        logger.warning(f"Intento de editar pregunta {pk} de encuesta {question.survey.status} por {request.user.username}")
        return JsonResponse({
            'success': False, 
            'error': 'Solo se pueden editar preguntas en encuestas en estado borrador'
        }, status=403)
    
    try:
        data = json.loads(request.body)
        
        with transaction.atomic():
            # Actualizar campos básicos
            question.text = data.get('text', question.text)[:500]
            question.type = data.get('type', question.type)
            question.is_required = data.get('is_required', question.is_required)
            question.save()
            
            # Si el tipo es single o multi, actualizar opciones
            if question.type in ['single', 'multi']:
                options_data = data.get('options', [])
                if options_data:
                    # Eliminar opciones antiguas
                    question.options.all().delete()
                    
                    # Crear nuevas opciones
                    for idx, option_text in enumerate(options_data):
                        if option_text.strip():
                            AnswerOption.objects.create(
                                question=question,
                                text=option_text.strip(),
                                order=idx
                            )
        
        logger.info(f"Pregunta {pk} actualizada por usuario {request.user.username}")
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Error al actualizar pregunta {pk}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def delete_question_view(request, pk):
    """Eliminar una pregunta (AJAX)."""
    try:
        question = get_object_or_404(Question.objects.select_related('survey'), pk=pk)
    except Http404:
        logger.warning(f"Intento de eliminar pregunta inexistente: ID {pk} por usuario {request.user.username}")
        return JsonResponse({'success': False, 'error': 'Pregunta no encontrada'}, status=404)
    
    # Verificar permisos
    if question.survey.author != request.user:
        logger.warning(f"Usuario {request.user.username} intentó eliminar pregunta {pk} sin permisos")
        return JsonResponse({'success': False, 'error': 'Sin permisos'}, status=403)
    
    # Validar que la encuesta esté en borrador
    if question.survey.status != 'draft':
        logger.warning(f"Intento de eliminar pregunta {pk} de encuesta {question.survey.status} por {request.user.username}")
        return JsonResponse({
            'success': False, 
            'error': 'Solo se pueden eliminar preguntas en encuestas en estado borrador'
        }, status=403)
    
    try:
        survey_id = question.survey.id
        question.delete()
        logger.info(f"Pregunta {pk} eliminada de encuesta {survey_id} por usuario {request.user.username}")
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Error al eliminar pregunta {pk}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def add_question_view(request, survey_pk):
    """Agregar una nueva pregunta a una encuesta (AJAX)."""
    try:
        survey = get_object_or_404(Survey, pk=survey_pk)
    except Http404:
        logger.warning(f"Intento de agregar pregunta a encuesta inexistente: ID {survey_pk} por usuario {request.user.username}")
        return JsonResponse({'success': False, 'error': 'Encuesta no encontrada'}, status=404)
    
    # Verificar permisos
    if survey.author != request.user:
        logger.warning(f"Usuario {request.user.username} intentó agregar pregunta a encuesta {survey_pk} sin permisos")
        return JsonResponse({'success': False, 'error': 'Sin permisos'}, status=403)
    
    # Validar que la encuesta esté en borrador
    if survey.status != 'draft':
        logger.warning(f"Intento de agregar pregunta a encuesta {survey.status} {survey_pk} por {request.user.username}")
        return JsonResponse({
            'success': False, 
            'error': 'Solo se pueden agregar preguntas a encuestas en estado borrador'
        }, status=403)
    
    try:
        data = json.loads(request.body)
        
        # Obtener el orden máximo actual
        max_order = survey.questions.count()
        
        question = Question.objects.create(
            survey=survey,
            text=data.get('text', 'Nueva pregunta')[:500],
            type=data.get('type', 'text'),
            is_required=data.get('is_required', False),
            order=max_order
        )
        
        logger.info(f"Nueva pregunta {question.id} creada en encuesta {survey_pk} por usuario {request.user.username}")
        return JsonResponse({
            'success': True,
            'question_id': question.id
        })
        
    except Exception as e:
        logger.error(f"Error al crear pregunta en encuesta {survey_pk}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
