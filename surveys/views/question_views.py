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
from asgiref.sync import sync_to_async

from surveys.models import Survey, Question, AnswerOption

logger = logging.getLogger('surveys')


@login_required
@require_POST
async def update_question_view(request, pk):
    """Actualizar una pregunta existente (AJAX)."""
    try:
        question = await sync_to_async(get_object_or_404, thread_sensitive=True)(Question.objects.select_related('survey'), pk=pk)
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
        @sync_to_async
        def update_question():
            with transaction.atomic():
                question.text = data.get('text', question.text)[:500]
                question.type = data.get('type', question.type)
                question.is_required = data.get('is_required', question.is_required)
                question.save()
                if question.type in ['single', 'multi']:
                    options_data = data.get('options', [])
                    if options_data:
                        question.options.all().delete()
                        for idx, option_text in enumerate(options_data):
                            if option_text.strip():
                                AnswerOption.objects.create(
                                    question=question,
                                    text=option_text.strip(),
                                    order=idx
                                )
        await update_question()
        logger.info(f"Pregunta {pk} actualizada por usuario {request.user.username}")
        return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"Error al actualizar pregunta {pk}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
async def delete_question_view(request, pk):
    """Eliminar una pregunta (AJAX)."""
    try:
        question = await sync_to_async(get_object_or_404, thread_sensitive=True)(Question.objects.select_related('survey'), pk=pk)
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
        @sync_to_async
        def delete_and_reorder():
            survey = question.survey
            question.delete()
            questions = survey.questions.order_by('order')
            for idx, q in enumerate(questions, start=1):
                if q.order != idx:
                    q.order = idx
                    q.save(update_fields=["order"])
        await delete_and_reorder()
        logger.info(f"Pregunta {pk} eliminada de encuesta {question.survey.id} por usuario {request.user.username} y preguntas reordenadas")
        return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"Error al eliminar pregunta {pk}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
async def add_question_view(request, public_id):
    """Agregar una nueva pregunta a una encuesta (AJAX)."""
    try:
        survey = await sync_to_async(get_object_or_404, thread_sensitive=True)(Survey, public_id=public_id)
    except Http404:
        logger.warning(f"Intento de agregar pregunta a encuesta inexistente: ID {public_id} por usuario {request.user.username}")
        return JsonResponse({'success': False, 'error': 'Encuesta no encontrada'}, status=404)
    
    # Verificar permisos
    if survey.author != request.user:
        logger.warning(f"Usuario {request.user.username} intentó agregar pregunta a encuesta {public_id} sin permisos")
        return JsonResponse({'success': False, 'error': 'Sin permisos'}, status=403)
    
    # Validar que la encuesta esté en borrador
    if survey.status != 'draft':
        logger.warning(f"Intento de agregar pregunta a encuesta {survey.status} {public_id} por {request.user.username}")
        return JsonResponse({
            'success': False, 
            'error': 'Solo se pueden agregar preguntas a encuestas en estado borrador'
        }, status=403)
    
    try:
        data = json.loads(request.body)
        @sync_to_async
        def create_question():
            next_order = survey.questions.count() + 1
            question = Question.objects.create(
                survey=survey,
                text=data.get('text', 'Nueva pregunta')[:500],
                type=data.get('type', 'text'),
                is_required=data.get('is_required', False),
                order=next_order
            )
            return question
        question = await create_question()
        logger.info(f"Nueva pregunta {question.id} creada en encuesta {public_id} por usuario {request.user.username}")
        return JsonResponse({
            'success': True,
            'question_id': question.id
        })
    except Exception as e:
        logger.error(f"Error al crear pregunta en encuesta {public_id}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
