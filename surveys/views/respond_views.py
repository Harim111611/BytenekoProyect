# surveys/views/respond_views.py
import logging
import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django_ratelimit.decorators import ratelimit

from surveys.models import Survey, SurveyResponse, QuestionResponse, AnswerOption
from core.validators import ResponseValidator
from core.utils.helpers import PermissionHelper

logger = logging.getLogger("surveys")


@ratelimit(key="ip", rate="60/h", method="POST", block=True)
def respond_survey_view(request, public_id):
    """
    Vista pública para responder una encuesta.

    Cambios implementados:
    - Se genera 'logic_map' JSON para manejar preguntas condicionales en el template.
    - Se pasa 'logic_map_json' al contexto.
    """
    try:
        # Optimizamos la query para traer preguntas y opciones en una sola vuelta
        survey = get_object_or_404(
            Survey.objects.select_related("author").prefetch_related("questions__options"),
            public_id=public_id,
        )
    except Http404:
        return render(
            request,
            "surveys/crud/not_found.html",
            {"survey_id": public_id},
            status=404,
        )

    # Encuesta no activa (cerrada, pausada, fuera de ventana, etc.)
    if not PermissionHelper.verify_survey_is_active(survey):
        messages.warning(request, "Esta encuesta no está activa actualmente.")
        return redirect(
            f"{reverse('surveys:thanks')}?public_id={survey.public_id}&status={survey.status}"
        )

    # --- LÓGICA CONDICIONAL PARA EL FRONTEND (NUEVO) ---
    # Construimos un mapa JSON para que JavaScript sepa qué ocultar/mostrar
    questions = survey.questions.all().order_by('order')  # Asegurar orden
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
            with transaction.atomic():
                # Usuario autenticado o respuesta anónima
                user_obj = request.user if request.user.is_authenticated else None

                survey_response = SurveyResponse.objects.create(
                    survey=survey,
                    user=user_obj,
                    is_anonymous=(user_obj is None),
                )

                # Usamos la lista de preguntas ya cargada en memoria
                questions_cached = list(questions)

                # --- FASE 1: recolectar IDs de opciones seleccionadas ---
                all_raw_option_ids = []
                for q in questions_cached:
                    field_name = f"pregunta_{q.id}"
                    if q.type == "multi":
                        all_raw_option_ids.extend(request.POST.getlist(field_name))
                    elif q.type == "single":
                        val = request.POST.get(field_name)
                        if val:
                            all_raw_option_ids.append(val)

                # Traemos todas las opciones involucradas en una sola query
                options_map = {
                    str(op.id): op
                    for op in AnswerOption.objects.filter(id__in=all_raw_option_ids)
                }

                # --- FASE 2: crear QuestionResponse válidas ---
                responses_to_create = []

                for q in questions_cached:
                    field = f"pregunta_{q.id}"

                    # Nota: Aquí se podría validar logic_map para no guardar respuestas de preguntas ocultas.
                    # Por robustez, procesamos lo que envía el formulario.

                    # Selección múltiple
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

                    # Selección única
                    elif q.type == "single":
                        raw_id = request.POST.get(field)
                        if raw_id:
                            opt = options_map.get(str(raw_id))
                            if opt and opt.question_id == q.id:
                                responses_to_create.append(
                                    QuestionResponse(
                                        survey_response=survey_response,
                                        question=q,
                                        selected_option=opt, # Guardamos la FK para facilitar análisis
                                        text_value=opt.text,
                                    )
                                )
                            elif opt:
                                logger.warning(
                                    "Intento de inyección de opción %s ajena a pregunta %s",
                                    raw_id,
                                    q.id,
                                )

                    # Numérica
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
                                pass # Ignoramos valores inválidos

                    # Texto libre / otros tipos
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

                # Bulk insert de respuestas
                QuestionResponse.objects.bulk_create(responses_to_create)

                # --- Auto pausa por meta de respuestas -------------------------
                original_status = survey.status
                if getattr(survey, "sample_goal", 0) and survey.sample_goal > 0:
                    total_responses = SurveyResponse.objects.filter(survey=survey).count()

                    if (
                        total_responses >= survey.sample_goal
                        and survey.status == Survey.STATUS_ACTIVE
                    ):
                        survey.status = Survey.STATUS_PAUSED
                        survey.save(update_fields=["status"])
                        logger.info(
                            "Encuesta %s pausada automáticamente al alcanzar la meta de %s respuestas",
                            survey.id,
                            survey.sample_goal,
                        )

                logger.info("Respuesta registrada encuesta %s", survey.id)

                # Mantenemos el status original para el mensaje de éxito
                final_status = original_status
                
                return redirect(
                    f"{reverse('surveys:thanks')}?"
                    f"public_id={survey.public_id}&status={final_status}&success=1"
                )

        except Exception as e:
            logger.exception("Error respondiendo encuesta %s: %s", public_id, e)
            messages.error(request, "Error guardando respuesta. Intenta nuevamente.")

    # GET → mostrar formulario con el contexto actualizado
    return render(request, "surveys/responses/fill.html", context)