"""
Utilidades de importación masiva usando PostgreSQL COPY FROM.
Alto rendimiento para insertar grandes volúmenes de datos.
Soporta psycopg2 (copy_expert) y psycopg 3 (copy).
"""


import io
import pandas as pd
from datetime import datetime

from django.db import transaction, connection
from django.utils import timezone
from django.conf import settings

from surveys.models import (
    Survey,
    Question,
    AnswerOption,
    SurveyResponse,
    QuestionResponse,
)


def bulk_import_responses_postgres(survey, dataframe_or_chunk, questions_map, date_column=None):
    """
    Importa respuestas usando ORM + bulk_create, procesando por batch/chunk.

    - Mantiene el uso de RAM bajo (solo se procesa el chunk actual).
    - Crea SurveyResponse y QuestionResponse para cada fila/columna.
    - Usa questions_map enriquecido:
        questions_map[col_name] = {
            "question": Question,
            "dtype": "single" | "multi" | "number" | "scale" | "text",
            "options": { "valor": AnswerOption, ... }  # opcional
        }
    Devuelve: (num_survey_responses, num_question_responses)
    """

    # Convertir el chunk actual a lista de dicts
    rows = dataframe_or_chunk.to_dict("records")
    total_rows = len(rows)
    if total_rows == 0:
        return 0, 0

    chunk_size = getattr(settings, 'SURVEY_IMPORT_CHUNK_SIZE', 1000)
    
    # Pre-cachear created_at para evitar llamadas repetidas a datetime.now()
    base_created_at = datetime.now()
    if timezone.is_naive(base_created_at):
        base_created_at = timezone.make_aware(base_created_at)
    
    with transaction.atomic():
        # OPTIMIZACIÓN: Desactivar espera de disco para velocidad extrema
        # Riesgo aceptable: Si la DB crashea <500ms después, se pierden estos datos (el usuario reintenta).
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL synchronous_commit TO OFF;")
        
        # 1) Crear SurveyResponse en bloque
        survey_responses = []

        for row in rows:
            created_at = base_created_at

            if date_column and date_column in row and row[date_column]:
                try:
                    val = row[date_column]
                    if not pd.isna(val):
                        dt = pd.to_datetime(val)
                        created_at = dt.to_pydatetime()
                        # Asegurar que created_at sea aware si USE_TZ=True
                        if timezone.is_naive(created_at):
                            created_at = timezone.make_aware(created_at)
                except (ValueError, TypeError):
                    # Si falla, usamos base_created_at
                    created_at = base_created_at

            survey_responses.append(
                SurveyResponse(
                    survey=survey,
                    user=None,          # respuestas anónimas
                    created_at=created_at,
                    is_anonymous=True,
                )
            )

        SurveyResponse.objects.bulk_create(survey_responses, batch_size=chunk_size)

        # 2) Crear QuestionResponse en bloque
        answer_objects = []
        new_options_to_create = []  # Para crear opciones en batch

        for idx, row in enumerate(rows):
            sr = survey_responses[idx]

            for column_name, value in row.items():
                # Ignorar columnas no mapeadas
                if column_name not in questions_map:
                    continue

                # Ignorar NaN o cadenas vacías
                if value is None or (isinstance(value, float) and pd.isna(value)):
                    continue
                if isinstance(value, str) and not value.strip():
                    continue

                qdata = questions_map[column_name]
                question = qdata.get("question")
                dtype = qdata.get("dtype", "text")
                options = qdata.get("options", {}) or {}

                # SINGLE CHOICE
                if dtype == "single":
                    val_str = str(value).strip()
                    option = options.get(val_str)

                    if option is None:
                        # Crear nueva opción en memoria, se guardará en batch después
                        option = AnswerOption(
                            question=question,
                            text=val_str,
                            order=len(options) + len(new_options_to_create) + 1,
                        )
                        new_options_to_create.append(option)
                        options[val_str] = option  # actualizar cache en questions_map

                    answer_objects.append(
                        QuestionResponse(
                            survey_response=sr,
                            question=question,
                            selected_option=option,
                            numeric_value=None,
                            text_value=None,
                        )
                    )

                # MULTI CHOICE (valores separados por coma)
                elif dtype == "multi":
                    parts = str(value).split(",")
                    for part in parts:
                        val_str = part.strip()
                        if not val_str:
                            continue
                        option = options.get(val_str)
                        if option is None:
                            option = AnswerOption(
                                question=question,
                                text=val_str,
                                order=len(options) + len(new_options_to_create) + 1,
                            )
                            new_options_to_create.append(option)
                            options[val_str] = option
                        answer_objects.append(
                            QuestionResponse(
                                survey_response=sr,
                                question=question,
                                selected_option=option,
                                numeric_value=None,
                                text_value=None,
                            )
                        )

                # NUMERIC / SCALE
                elif dtype in ["number", "scale"]:
                    try:
                        num_val = float(value)
                    except (ValueError, TypeError):
                        continue

                    answer_objects.append(
                        QuestionResponse(
                            survey_response=sr,
                            question=question,
                            selected_option=None,
                            numeric_value=num_val,
                            text_value=None,
                        )
                    )

                # TEXT (default)
                else:
                    text_val = str(value)
                    text_val = text_val.replace("\t", " ").replace("\n", " ").strip()
                    text_val = text_val[:500]

                    if not text_val:
                        continue

                    answer_objects.append(
                        QuestionResponse(
                            survey_response=sr,
                            question=question,
                            selected_option=None,
                            numeric_value=None,
                            text_value=text_val,
                        )
                    )

        # Crear nuevas opciones en batch ANTES de crear las respuestas
        if new_options_to_create:
            AnswerOption.objects.bulk_create(new_options_to_create, batch_size=chunk_size)

        if answer_objects:
            QuestionResponse.objects.bulk_create(answer_objects, batch_size=chunk_size)

    return len(survey_responses), len(answer_objects)