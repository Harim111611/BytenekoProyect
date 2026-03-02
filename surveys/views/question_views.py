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
        question = await sync_to_async(get_object_or_404, thread_sensitive=True)(
            Question.objects.select_related('survey__author'),
            pk=pk,
        )
    except Http404:
        logger.warning("Intento de actualizar pregunta inexistente: ID %s por usuario %s", pk, request.user.username)
        return JsonResponse({'success': False, 'error': 'Pregunta no encontrada'}, status=404)
    
    # Verificar permisos (solo el autor puede editar)
    if question.survey.author != request.user:
        logger.warning("Usuario %s intentó editar pregunta %s sin permisos", request.user.username, pk)
        return JsonResponse({'success': False, 'error': 'Sin permisos'}, status=403)
    
    # Validar que la encuesta esté en borrador
    if question.survey.status != 'draft':
        logger.warning("Intento de editar pregunta %s de encuesta %s por %s", pk, question.survey.status, request.user.username)
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
        logger.info("Pregunta %s actualizada por usuario %s", pk, request.user.username)
        return JsonResponse({'success': True})
    except Exception:
        logger.exception("Error al actualizar pregunta %s", pk)
        return JsonResponse({'success': False, 'error': 'Error interno actualizando pregunta'}, status=500)


@login_required
@require_POST
async def delete_question_view(request, pk):
    """Eliminar una pregunta (AJAX)."""
    try:
        question = await sync_to_async(get_object_or_404, thread_sensitive=True)(
            Question.objects.select_related('survey__author'),
            pk=pk,
        )
    except Http404:
        logger.warning("Intento de eliminar pregunta inexistente: ID %s por usuario %s", pk, request.user.username)
        return JsonResponse({'success': False, 'error': 'Pregunta no encontrada'}, status=404)
    
    # Verificar permisos
    if question.survey.author != request.user:
        logger.warning("Usuario %s intentó eliminar pregunta %s sin permisos", request.user.username, pk)
        return JsonResponse({'success': False, 'error': 'Sin permisos'}, status=403)
    
    # Validar que la encuesta esté en borrador
    if question.survey.status != 'draft':
        logger.warning("Intento de eliminar pregunta %s de encuesta %s por %s", pk, question.survey.status, request.user.username)
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
        logger.info("Pregunta %s eliminada de encuesta %s por usuario %s y preguntas reordenadas", pk, question.survey.id, request.user.username)
        return JsonResponse({'success': True})
    except Exception:
        logger.exception("Error al eliminar pregunta %s", pk)
        return JsonResponse({'success': False, 'error': 'Error interno eliminando pregunta'}, status=500)


@login_required
@require_POST
async def add_question_view(request, public_id):
    """Agregar una nueva pregunta a una encuesta (AJAX)."""
    try:
        # NOTE: En contexto async no debemos disparar queries al acceder a survey.author.
        # select_related('author') garantiza que el FK ya viene cargado.
        survey = await sync_to_async(get_object_or_404, thread_sensitive=True)(
            Survey.objects.select_related('author'),
            public_id=public_id,
        )
    except Http404:
        logger.warning("Intento de agregar pregunta a encuesta inexistente: ID %s por usuario %s", public_id, request.user.username)
        return JsonResponse({'success': False, 'error': 'Encuesta no encontrada'}, status=404)
    
    # Verificar permisos
    if survey.author != request.user:
        logger.warning("Usuario %s intentó agregar pregunta a encuesta %s sin permisos", request.user.username, public_id)
        return JsonResponse({'success': False, 'error': 'Sin permisos'}, status=403)
    
    # Validar que la encuesta esté en borrador
    if survey.status != 'draft':
        logger.warning("Intento de agregar pregunta a encuesta %s %s por %s", survey.status, public_id, request.user.username)
        return JsonResponse({
            'success': False, 
            'error': 'Solo se pueden agregar preguntas a encuestas en estado borrador'
        }, status=403)
    
    try:
        data = json.loads(request.body)
        @sync_to_async
        def create_question():
            next_order = survey.questions.count() + 1
            question_type = data.get('type', 'text')
            question = Question.objects.create(
                survey=survey,
                text=data.get('text', 'Nueva pregunta')[:500],
                type=question_type,
                is_required=data.get('is_required', False),
                order=next_order
            )

            if question_type in ['single', 'multi']:
                options_data = data.get('options', [])
                if isinstance(options_data, list):
                    for idx, option_text in enumerate(options_data):
                        if str(option_text).strip():
                            AnswerOption.objects.create(
                                question=question,
                                text=str(option_text).strip(),
                                order=idx,
                            )
            return question
        question = await create_question()
        logger.info("Nueva pregunta %s creada en encuesta %s por usuario %s", question.id, public_id, request.user.username)
        return JsonResponse({
            'success': True,
            'question_id': question.id
        })
    except Exception:
        logger.exception("Error al crear pregunta en encuesta %s", public_id)
        return JsonResponse({'success': False, 'error': 'Error interno creando pregunta'}, status=500)
