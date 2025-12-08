# surveys/views/respond_views.py
import logging

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

    - Valida que la encuesta esté activa.
    - Crea un SurveyResponse asociado al usuario (si está autenticado) o anónimo.
    - Crea QuestionResponse en bulk.
    - Si hay sample_goal (> 0) y se alcanza o supera al guardar esta respuesta,
      pausa automáticamente la encuesta (status = PAUSED).
    """
    try:
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

                questions_cached = list(survey.questions.all())

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

                options_map = {
                    str(op.id): op
                    for op in AnswerOption.objects.filter(id__in=all_raw_option_ids)
                }

                # --- FASE 2: crear QuestionResponse válidas ---
                responses_to_create = []

                for q in questions_cached:
                    field = f"pregunta_{q.id}"

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
                                # Si no es válido simplemente no se guarda
                                pass

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
                # Si sample_goal > 0 y se alcanza o supera, pausamos la encuesta.
                # Guardamos el estado original para que la vista de 'thanks'
                # muestre el mensaje de agradecimiento en la última respuesta,
                # incluso si la encuesta se pasa a PAUSED tras guardar.
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
                            "Encuesta %s pausada automáticamente al alcanzar la meta "
                            "de %s respuestas (total=%s)",
                            survey.id,
                            survey.sample_goal,
                            total_responses,
                        )

                logger.info("Respuesta registrada encuesta %s", survey.id)

                # Usar el estado original en la redirección para que el mensaje
                # final muestre 'gracias' cuando la respuesta fue válida, aun
                # cuando la encuesta se pause automáticamente al alcanzar la meta.
                final_status = original_status if 'original_status' in locals() else survey.status
                return redirect(
                    f"{reverse('surveys:thanks')}?"
                    f"public_id={survey.public_id}&status={final_status}&success=1"
                )

        except Exception as e:
            logger.exception("Error respondiendo encuesta %s: %s", public_id, e)
            messages.error(request, "Error guardando respuesta. Intenta nuevamente.")

    # GET → mostrar formulario público de la encuesta
    return render(request, "surveys/responses/fill.html", {"survey": survey})
