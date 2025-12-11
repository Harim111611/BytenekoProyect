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
    
    Mejoras implementadas:
    - Validación estricta de lógica condicional en el servidor (Server-Side Logic).
    - Prevención de inyección de datos en preguntas ocultas.
    - Optimización de consultas SQL (prefetch_related).
    - Atomicidad en la transacción de guardado.
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

    # Verificar si la encuesta está activa (cerrada, pausada, fuera de ventana, etc.)
    if not PermissionHelper.verify_survey_is_active(survey):
        messages.warning(request, "Esta encuesta no está activa actualmente.")
        return redirect(
            f"{reverse('surveys:thanks')}?public_id={survey.public_id}&status={survey.status}"
        )

    # --- PREPARACIÓN DE DATOS (Orden garantizado) ---
    # Convertimos a lista para iterar sin re-consultar la BD
    questions_list = list(survey.questions.all().order_by('order'))
    
    # Construimos el mapa lógico para el Frontend (JavaScript)
    logic_map = {}
    for q in questions_list:
        if q.depends_on:
            logic_map[q.id] = {
                'parent_id': q.depends_on.id,
                'trigger_option_id': q.visible_if_option.id if q.visible_if_option else None,
                'condition': 'equals'
            }
    
    context = {
        "survey": survey,
        "logic_map_json": json.dumps(logic_map) 
    }

    if request.method == "POST":
        try:
            with transaction.atomic():
                # 1. Crear la cabecera de la respuesta
                user_obj = request.user if request.user.is_authenticated else None
                survey_response = SurveyResponse.objects.create(
                    survey=survey,
                    user=user_obj,
                    is_anonymous=(user_obj is None),
                )

                # --- VALIDACIÓN DE LÓGICA DEL SERVIDOR (Evaluador Secuencial) ---
                # Rastreamos qué opciones ha seleccionado el usuario para validar dependencias
                # Formato: { question_id: selected_option_id }
                user_selection_map = {}
                
                # Optimización: Recolectar todos los valores enviados para hacer una sola query de Opciones
                all_post_values = []
                for q in questions_list:
                    # Buscamos tanto valores simples como listas (multi-select)
                    raw_val = request.POST.get(f"pregunta_{q.id}")
                    raw_list = request.POST.getlist(f"pregunta_{q.id}")
                    if raw_val: all_post_values.append(raw_val)
                    if raw_list: all_post_values.extend(raw_list)
                
                # Diccionario de opciones válidas traídas de la BD
                valid_options_db = {
                    str(opt.id): opt for opt in AnswerOption.objects.filter(id__in=all_post_values)
                }

                responses_to_create = []

                # Iteramos las preguntas EN ORDEN para respetar la cadena de dependencia lógica
                for q in questions_list:
                    
                    # A. Verificar Visibilidad (Lógica Condicional)
                    is_visible = True
                    if q.depends_on:
                        parent_selection = user_selection_map.get(q.depends_on.id)
                        required_option = q.visible_if_option.id if q.visible_if_option else None
                        
                        # Si la selección de la pregunta padre no coincide con la requerida, ocultar.
                        if parent_selection != required_option:
                            is_visible = False
                    
                    # Si la pregunta está oculta por lógica, NO guardamos nada (aunque venga en el POST)
                    if not is_visible:
                        continue 

                    # B. Procesar y Validar Respuesta
                    field_name = f"pregunta_{q.id}"
                    
                    # Caso 1: Selección Múltiple
                    if q.type == "multi":
                        raw_ids = request.POST.getlist(field_name)
                        valid_texts = []
                        for rid in raw_ids:
                            opt = valid_options_db.get(str(rid))
                            # Validar que la opción pertenece a esta pregunta específica
                            if opt and opt.question_id == q.id:
                                valid_texts.append(opt.text)
                            elif opt:
                                logger.warning(f"Intento de inyección: Opción {rid} no pertenece a pregunta {q.id}")
                        
                        if valid_texts:
                            responses_to_create.append(QuestionResponse(
                                survey_response=survey_response,
                                question=q,
                                text_value=",".join(valid_texts)
                            ))

                    # Caso 2: Selección Única
                    elif q.type == "single":
                        raw_id = request.POST.get(field_name)
                        if raw_id:
                            opt = valid_options_db.get(str(raw_id))
                            if opt and opt.question_id == q.id:
                                # Guardamos selección en el mapa para evaluar preguntas hijas futuras
                                user_selection_map[q.id] = opt.id
                                
                                responses_to_create.append(QuestionResponse(
                                    survey_response=survey_response,
                                    question=q,
                                    selected_option=opt,
                                    text_value=opt.text
                                ))

                    # Caso 3: Numérico
                    elif q.type == "numeric":
                        val = request.POST.get(field_name)
                        if val not in (None, ""):
                            try:
                                if getattr(q, "allow_decimal", False):
                                    validated = ResponseValidator.validate_decimal_response(val)
                                    # Guardamos como float o int según corresponda la lógica de negocio, aquí int simplificado
                                    num_val = int(float(validated))
                                else:
                                    validated = ResponseValidator.validate_numeric_response(val)
                                    num_val = int(validated)
                                    
                                responses_to_create.append(QuestionResponse(
                                    survey_response=survey_response,
                                    question=q,
                                    numeric_value=num_val
                                ))
                            except (ValidationError, ValueError):
                                pass # Ignoramos valores numéricos inválidos

                    # Caso 4: Texto libre / Escala / Otros
                    else:
                        val = request.POST.get(field_name)
                        validated = ResponseValidator.validate_text_response(val)
                        if validated:
                            responses_to_create.append(QuestionResponse(
                                survey_response=survey_response,
                                question=q,
                                text_value=validated
                            ))

                # Insert masivo de respuestas validadas
                QuestionResponse.objects.bulk_create(responses_to_create)

                # --- LÓGICA DE META DE MUESTRA (Auto-Pausa) ---
                original_status = survey.status
                if survey.sample_goal > 0 and survey.status == Survey.STATUS_ACTIVE:
                    # Contamos de nuevo para asegurar consistencia
                    current_count = SurveyResponse.objects.filter(survey=survey).count()
                    if current_count >= survey.sample_goal:
                        survey.status = Survey.STATUS_PAUSED
                        survey.save(update_fields=["status"])
                        logger.info(f"Encuesta {survey.id} pausada automáticamente. Meta: {survey.sample_goal}")

                logger.info(f"Respuesta registrada exitosamente para encuesta {survey.id}")

                # Redirección final
                return redirect(
                    f"{reverse('surveys:thanks')}?"
                    f"public_id={survey.public_id}&status={original_status}&success=1"
                )

        except Exception as e:
            logger.exception(f"Error crítico respondiendo encuesta {public_id}: {e}")
            messages.error(request, "Error guardando respuesta. Intenta nuevamente.")

    # GET → Renderizar formulario
    return render(request, "surveys/responses/fill.html", context)