# surveys/views/respond_views.py
import logging
import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django_ratelimit.decorators import ratelimit

from surveys.models import Survey, SurveyResponse, QuestionResponse, AnswerOption
from core.validators import ResponseValidator
from core.utils.helpers import PermissionHelper

logger = logging.getLogger("surveys")


from asgiref.sync import sync_to_async

@ratelimit(key="ip", rate="60/h", method="POST", block=True)
async def respond_survey_view(request, public_id):
    """
    Vista pública para responder una encuesta.

    Cambios implementados:
    - Se genera 'logic_map' JSON para manejar preguntas condicionales en el template.
    - Se pasa 'logic_map_json' al contexto.
    """
    try:
        # Optimizamos la query para traer preguntas y opciones en una sola vuelta
        survey = await sync_to_async(get_object_or_404, thread_sensitive=True)(
            Survey.objects.select_related("author").prefetch_related("questions__options"),
            public_id=public_id,
        )
    except Http404:
        render_async = sync_to_async(render, thread_sensitive=True)
        return await render_async(
            request,
            "surveys/crud/not_found.html",
            {"survey_id": public_id},
            status=404,
        )

    # Encuesta no activa (cerrada, pausada, fuera de ventana, etc.)
    if not PermissionHelper.verify_survey_is_active(survey):
        await sync_to_async(messages.warning, thread_sensitive=True)(request, "Esta encuesta no está activa actualmente.")
        redirect_async = sync_to_async(redirect, thread_sensitive=True)
        url = f"{reverse('surveys:thanks')}?public_id={survey.public_id}&status={survey.status}"
        return await redirect_async(url)

    # --- LÓGICA CONDICIONAL PARA EL FRONTEND (NUEVO) ---
    # Construimos un mapa JSON para que JavaScript sepa qué ocultar/mostrar
    questions = await sync_to_async(lambda: list(survey.questions.all().order_by('order')), thread_sensitive=True)()  # Asegurar orden
    logic_map = {}
    
    for q in questions:
        if q.depends_on:
            logic_map[q.id] = {
                'parent_id': q.depends_on.id,
                'trigger_option_id': q.visible_if_option.id if q.visible_if_option else None,
                'condition': 'equals'  # Por defecto validamos igualdad de opción
            }
    
    context = {
        "survey": survey,
        "logic_map_json": json.dumps(logic_map) 
    }
    # ----------------------------------------------------

    if request.method == "POST":
        try:
            @sync_to_async
            def create_survey_response():
                user_obj = request.user if request.user.is_authenticated else None
                return SurveyResponse.objects.create(
                    survey=survey,
                    user=user_obj,
                    is_anonymous=(user_obj is None),
                )
            survey_response = await create_survey_response()
            questions_cached = list(questions)
            all_raw_option_ids = []
            for q in questions_cached:
                field_name = f"pregunta_{q.id}"
                if q.type == "multi":
                    all_raw_option_ids.extend(request.POST.getlist(field_name))
                elif q.type == "single":
                    val = request.POST.get(field_name)
                    if val:
                        all_raw_option_ids.append(val)
            @sync_to_async
            def get_options_map():
                return {
                    str(op.id): op
                    for op in AnswerOption.objects.filter(id__in=all_raw_option_ids)
                }
            options_map = await get_options_map()
            responses_to_create = []
            for q in questions_cached:
                field = f"pregunta_{q.id}"
                if q.type == "multi":
                    raw_ids = request.POST.getlist(field)
                    valid_texts = []
                    for rid in raw_ids:
                        opt = options_map.get(str(rid))
                        if opt and opt.question_id == q.id:
                            valid_texts.append(opt.text)
                        elif opt:
                            logger.warning(
                                "Intento de inyección de opción %s ajena a pregunta %s",
                                rid,
                                q.id,
                            )
                    if valid_texts:
                        responses_to_create.append(
                            QuestionResponse(
                                survey_response=survey_response,
                                question=q,
                                text_value=",".join(valid_texts),
                            )
                        )
                elif q.type == "single":
                    raw_id = request.POST.get(field)
                    if raw_id:
                        opt = options_map.get(str(raw_id))
                        if opt and opt.question_id == q.id:
                            responses_to_create.append(
                                QuestionResponse(
                                    survey_response=survey_response,
                                    question=q,
                                    selected_option=opt,
                                    text_value=opt.text,
                                )
                            )
                        elif opt:
                            logger.warning(
                                "Intento de inyección de opción %s ajena a pregunta %s",
                                raw_id,
                                q.id,
                            )
                elif q.type == "numeric":
                    val = request.POST.get(field)
                    if val not in (None, ""):
                        try:
                            if getattr(q, "allow_decimal", False):
                                validated = ResponseValidator.validate_decimal_response(val)
                            else:
                                validated = ResponseValidator.validate_numeric_response(val)
                            responses_to_create.append(
                                QuestionResponse(
                                    survey_response=survey_response,
                                    question=q,
                                    numeric_value=int(validated),
                                )
                            )
                        except ValidationError:
                            pass
                else:
                    val = request.POST.get(field)
                    validated = ResponseValidator.validate_text_response(val)
                    if validated:
                        responses_to_create.append(
                            QuestionResponse(
                                survey_response=survey_response,
                                question=q,
                                text_value=validated,
                            )
                        )
            @sync_to_async
            def bulk_create_responses():
                QuestionResponse.objects.bulk_create(responses_to_create)
            await bulk_create_responses()
            original_status = survey.status
            if getattr(survey, "sample_goal", 0) and survey.sample_goal > 0:
                @sync_to_async
                def get_total_responses():
                    return SurveyResponse.objects.filter(survey=survey).count()
                total_responses = await get_total_responses()
                if (
                    total_responses >= survey.sample_goal
                    and survey.status == Survey.STATUS_ACTIVE
                ):
                    survey.status = Survey.STATUS_PAUSED
                    @sync_to_async
                    def save_survey():
                        survey.save(update_fields=["status"])
                    await save_survey()
                    logger.info(
                        "Encuesta %s pausada automáticamente al alcanzar la meta de %s respuestas",
                        survey.id,
                        survey.sample_goal,
                    )
            logger.info("Respuesta registrada encuesta %s", survey.id)
            final_status = original_status
            redirect_async = sync_to_async(redirect, thread_sensitive=True)
            url = (
                f"{reverse('surveys:thanks')}?"
                f"public_id={survey.public_id}&status={final_status}&success=1"
            )
            return await redirect_async(url)
        except Exception as e:
            logger.exception("Error respondiendo encuesta %s: %s", public_id, e)
            await sync_to_async(messages.error, thread_sensitive=True)(request, "Error guardando respuesta. Intenta nuevamente.")
    render_async = sync_to_async(render, thread_sensitive=True)
    return await render_async(request, "surveys/responses/fill.html", context)