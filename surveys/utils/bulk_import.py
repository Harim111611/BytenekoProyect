import csv
import io
import re
from datetime import datetime

import pandas as pd
from dateutil import parser
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from surveys.models import SurveyResponse, QuestionResponse


def parse_date_safe(date_str):
    """
    Intenta parsear un valor de fecha a un datetime timezone-aware.
    Devuelve None si el valor no se puede interpretar como fecha.
    """
    if pd.isna(date_str):
        return None

    value = str(date_str).strip()
    if not value:
        return None

    # Intento 1: pandas.to_datetime (acepta muchos formatos)
    try:
        dt = pd.to_datetime(value, errors="coerce")
        if pd.isna(dt):
            raise ValueError
        py_dt = dt.to_pydatetime()
        if timezone.is_naive(py_dt):
            py_dt = timezone.make_aware(py_dt)
        return py_dt
    except Exception:
        pass

    # Intento 2: dateutil.parser (más flexible todavía)
    try:
        dt = parser.parse(value)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt
    except Exception:
        return None


def _clean_numeric_value(raw: str):
    """
    Intenta extraer un número entero desde una cadena arbitraria.
    - Elimina caracteres no numéricos salvo signo y separador decimal.
    - Soporta '1,234', '1.234', '5.0', etc.
    Devuelve (num_value, text_fallback) donde solo uno de los dos
    estará informado.
    """
    s = str(raw).strip()
    if not s:
        return None, None

    # Si es algo muy claramente no numérico, devolvemos texto
    # (ej. 'No', 'N/A').
    if not any(ch.isdigit() for ch in s):
        return None, s

    # Normalizar coma decimal a punto
    s_norm = s.replace(",", ".")
    # Quedarnos solo con dígitos, signo y punto
    cleaned = "".join(ch for ch in s_norm if (ch.isdigit() or ch in ".-"))

    # Evitar casos patológicos como sólo '.' o '-'
    if cleaned in {"", ".", "-", "-."}:
        return None, s

    try:
        num_float = float(cleaned)
        # Guardamos como entero para simplificar análisis (ej. escalas 1–10)
        num_int = int(num_float)
        return num_int, None
    except Exception:
        return None, s


def _split_multi_value(value: str):
    """
    Divide respuestas múltiples usando coma o punto y coma como separadores.
    Ejemplo: 'A, B; C' => ['A', 'B', 'C']
    """
    if pd.isna(value):
        return []

    s = str(value).strip()
    if not s:
        return []

    parts = re.split(r"[;,]", s)
    return [p.strip() for p in parts if p.strip()]


def bulk_import_responses_postgres(survey, dataframe_or_chunk, questions_map, date_column=None):
    """
    Inserta masivamente respuestas a partir de un DataFrame.
    Usa COPY de PostgreSQL para QuestionResponse para maximizar rendimiento.

    Parámetros:
    - survey: instancia de Survey
    - dataframe_or_chunk: DataFrame completo o chunk
    - questions_map: dict {col_name: {"question": Question, "dtype": str, "options": {text: AnswerOption}}}
    - date_column: nombre de la columna que contiene la fecha/hora de respuesta (opcional)
    """
    if dataframe_or_chunk is None:
        return 0, 0

    rows = dataframe_or_chunk.to_dict("records")
    if not rows:
        return 0, 0

    chunk_size = getattr(settings, "SURVEY_IMPORT_CHUNK_SIZE", 2000)
    default_date = timezone.now()

    with transaction.atomic():
        # Desactivar synchronous_commit dentro de la transacción para acelerar COPY
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL synchronous_commit TO OFF;")

        # ------------------------------------------------------------
        # 1) Crear SurveyResponse por cada fila
        # ------------------------------------------------------------
        response_datetimes = []
        for row in rows:
            created_at = default_date
            if date_column and date_column in row:
                parsed = parse_date_safe(row.get(date_column))
                if parsed:
                    created_at = parsed
            response_datetimes.append(created_at)

        sr_objects = [
            SurveyResponse(survey=survey, created_at=dt, is_anonymous=True)
            for dt in response_datetimes
        ]
        created_srs = SurveyResponse.objects.bulk_create(sr_objects, batch_size=chunk_size)

        # ------------------------------------------------------------
        # 2) Construir buffer CSV para COPY de QuestionResponse
        # ------------------------------------------------------------
        qr_buffer = io.StringIO()
        qr_writer = csv.writer(
            qr_buffer,
            delimiter=",",
            quotechar='"',
            quoting=csv.QUOTE_MINIMAL,
        )

        final_rows_count = 0

        for idx, row in enumerate(rows):
            sr_id = created_srs[idx].id

            for col_name, raw_val in row.items():
                # Saltar columna de fecha
                if col_name == date_column:
                    continue

                # Sólo consideramos columnas que tienen una pregunta asociada
                if col_name not in questions_map:
                    continue

                if pd.isna(raw_val) or raw_val == "":
                    continue

                s_val = str(raw_val).strip()
                if not s_val:
                    continue

                q_data = questions_map[col_name]
                question = q_data["question"]
                dtype = q_data["dtype"]
                options_map = q_data.get("options", {})

                q_id = question.id
                so_id = "\\N"
                text_val = "\\N"
                num_val = "\\N"

                try:
                    if dtype == "single":
                        # Opción única: intentamos mapear a AnswerOption por texto
                        if s_val in options_map:
                            so_id = options_map[s_val].id
                        else:
                            # Si la opción no existe (typo, valor nuevo...), guardamos como texto
                            text_val = s_val.replace("\n", " ").replace("\r", "")[:5000]

                    elif dtype == "multi":
                        # Opción múltiple: podemos generar varias filas QuestionResponse
                        for part in _split_multi_value(s_val):
                            if part in options_map:
                                sub_so_id = options_map[part].id
                                qr_writer.writerow([sr_id, q_id, sub_so_id, "\\N", "\\N"])
                                final_rows_count += 1
                            else:
                                # Si no encaja con ninguna opción conocida, lo almacenamos como texto independiente
                                text_entry = part.replace("\n", " ").replace("\r", "")[:5000]
                                qr_writer.writerow([sr_id, q_id, "\\N", text_entry, "\\N"])
                                final_rows_count += 1
                        # Ya hemos generado las filas correspondientes a esta pregunta
                        continue

                    elif dtype in ("number", "scale"):
                        # Valores numéricos / de escala.
                        num, fallback_text = _clean_numeric_value(s_val)
                        if num is not None:
                            num_val = num
                        elif fallback_text is not None:
                            text_val = fallback_text.replace("\n", " ").replace("\r", "")[:5000]

                    else:
                        # Texto libre
                        text_val = s_val.replace("\n", " ").replace("\r", "")[:5000]

                    qr_writer.writerow([sr_id, q_id, so_id, text_val, num_val])
                    final_rows_count += 1

                except Exception:
                    # Nunca queremos detener todo el import por una fila problemática.
                    continue

        # ------------------------------------------------------------
        # 3) COPY a PostgreSQL
        # ------------------------------------------------------------
        qr_buffer.seek(0)
        table = QuestionResponse._meta.db_table
        cols = "(survey_response_id, question_id, selected_option_id, text_value, numeric_value)"
        sql = f"COPY {table} {cols} FROM STDIN WITH (FORMAT CSV, NULL '\\N')"

        with connection.cursor() as cursor:
            try:
                if hasattr(cursor, "copy_expert"):
                    cursor.copy_expert(sql, qr_buffer)
                elif hasattr(cursor, "copy"):
                    with cursor.copy(sql) as copy:
                        copy.write(qr_buffer.read())
                else:  # pragma: no cover - drivers antiguos
                    # Fallback muy lento, pero evita perder los datos
                    qr_buffer.seek(0)
                    reader = csv.reader(qr_buffer)
                    for row in reader:
                        (
                            sr_id,
                            q_id,
                            so_id,
                            text_value,
                            numeric_value,
                        ) = row
                        QuestionResponse.objects.create(
                            survey_response_id=int(sr_id),
                            question_id=int(q_id),
                            selected_option_id=None if so_id == "\\N" else int(so_id),
                            text_value=None if text_value == "\\N" else text_value,
                            numeric_value=None if numeric_value == "\\N" else int(numeric_value),
                        )
            except Exception as e:  # pragma: no cover - logging en producción
                print(f"[IMPORT][COPY_ERROR] {e}")

    return len(rows), final_rows_count
