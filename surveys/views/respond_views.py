# surveys/views/respond_views.py
"""
Views for public survey responses.
"""
import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, render, redirect
from django.http import Http404
from django_ratelimit.decorators import ratelimit

from surveys.models import Survey, SurveyResponse, QuestionResponse, AnswerOption
from core.validators import ResponseValidator
from core.utils.helpers import PermissionHelper

logger = logging.getLogger('surveys')


@ratelimit(key='ip', rate='60/h', method='POST', block=True)
def respond_survey_view(request, pk):
    """Vista para responder una encuesta pública."""
    try:
        survey = get_object_or_404(
            Survey.objects.prefetch_related('questions__options'),
            pk=pk
        )
    except Http404:
        logger.warning(f"Intento de acceso a encuesta inexistente: ID {pk} desde IP {request.META.get('REMOTE_ADDR')}")
        return render(request, 'surveys/not_found.html', {
            'survey_id': pk,
            'message': 'La encuesta que intentas responder no existe o ha sido eliminada.'
        }, status=404)

    # Validar que la encuesta esté activa usando helper
    if not PermissionHelper.verify_survey_is_active(survey):
        messages.warning(request, "Esta encuesta no está activa actualmente")
        return redirect('surveys:thanks')

    if request.method == 'POST':
        try:
            with transaction.atomic():
                user_obj = request.user if request.user.is_authenticated else None
                survey_response = SurveyResponse.objects.create(
                    survey=survey,
                    user=user_obj,
                    is_anonymous=(user_obj is None)
                )

                # OPTIMIZACIÓN: Cachear preguntas para evitar doble query
                questions_cached = list(survey.questions.prefetch_related('options').all())

                # Recopilar IDs de opciones para bulk fetch
                all_option_ids = []
                for q in questions_cached:
                    field = f'pregunta_{q.id}'
                    if q.type == 'multi':
                        opts = request.POST.getlist(field)
                        all_option_ids.extend(opts)
                    elif q.type == 'single':
                        val = request.POST.get(field)
                        if val:
                            all_option_ids.append(val)

                # Bulk fetch all options to avoid N+1
                options_map = {
                    str(op.id): op 
                    for op in AnswerOption.objects.filter(id__in=all_option_ids)
                }

                for q in questions_cached:
                    field = f'pregunta_{q.id}'
                    if q.type == 'multi':
                        opts = request.POST.getlist(field)
                        txts = [options_map[o].text for o in opts if o in options_map]
                        if txts:
                            QuestionResponse.objects.create(
                                survey_response=survey_response,
                                question=q,
                                text_value=",".join(txts)
                            )
                    else:
                        val = request.POST.get(field)
                        if val:
                            if q.type in ['number', 'scale']:
                                try:
                                    # Validar respuesta numérica
                                    if q.type == 'scale':
                                        validated_value = ResponseValidator.validate_scale_response(val)
                                    else:
                                        validated_value = ResponseValidator.validate_numeric_response(val)
                                    QuestionResponse.objects.create(
                                        survey_response=survey_response,
                                        question=q,
                                        numeric_value=int(validated_value)
                                    )
                                except ValidationError as e:
                                    logger.warning(f"Respuesta numérica inválida para pregunta {q.id}: {e}")
                                    # Continuar con otras preguntas
                            elif q.type == 'single':
                                option_obj = options_map.get(val)
                                if option_obj:
                                    QuestionResponse.objects.create(
                                        survey_response=survey_response,
                                        question=q,
                                        selected_option=option_obj
                                    )
                            else:
                                validated_text = ResponseValidator.validate_text_response(val)
                                if validated_text:
                                    QuestionResponse.objects.create(
                                        survey_response=survey_response,
                                        question=q,
                                        text_value=validated_text
                                    )

                logger.info(f"Respuesta registrada exitosamente para encuesta {survey.id}")
                return redirect('surveys:thanks')

        except ValidationError as e:
            logger.error(f"Error de validación al responder encuesta {pk}: {e}")
            messages.error(request, str(e))
        except Exception as e:
            logger.exception(f"Error inesperado al guardar respuesta de encuesta {pk}: {e}")
            messages.error(request, "Ocurrió un error al guardar su respuesta. Por favor intente nuevamente.")

    return render(request, 'surveys/fill.html', {'survey': survey})
