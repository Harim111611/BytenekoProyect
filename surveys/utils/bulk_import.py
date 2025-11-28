"""
Utilidades de importación masiva usando PostgreSQL COPY FROM.
Alto rendimiento para insertar grandes volúmenes de datos.
"""
import io
import pandas as pd
from datetime import datetime
from django.db import connection, transaction
from surveys.models import Survey, Question, AnswerOption, SurveyResponse, QuestionResponse


def bulk_import_responses_postgres(survey, dataframe, questions_map, date_column=None):
    """
    Importa respuestas usando PostgreSQL COPY FROM para máximo rendimiento.
    """
    rows = dataframe.to_dict('records')
    total_rows = len(rows)

    with transaction.atomic():
        with connection.cursor() as django_cursor:
            # ---------------------------------------------------------
            # 🛠️ CORRECCIÓN: Obtener el cursor 'crudo' de psycopg2
            # ---------------------------------------------------------
            # Django devuelve un 'CursorWrapper'. Necesitamos el objeto real 
            # de la librería psycopg2 para acceder a .copy_expert()
            pg_cursor = django_cursor.cursor
            
            # Si hay capas extra (como Django Debug Toolbar), seguimos bajando
            while hasattr(pg_cursor, 'cursor'):
                pg_cursor = pg_cursor.cursor
            
            # Verificación de seguridad
            if not hasattr(pg_cursor, 'copy_expert'):
                raise Exception(
                    "Error de Driver: No se encontró el método 'copy_expert'. "
                    "Asegúrate de estar usando PostgreSQL en settings.local."
                )

            # ---------------------------------------------------------
            # Paso 1: COPY para SurveyResponse
            # ---------------------------------------------------------
            survey_buffer = io.StringIO()
            
            for idx, row in enumerate(rows):
                created_at = datetime.now()
                
                if date_column and date_column in row and row[date_column]:
                    try:
                        val = row[date_column]
                        if not pd.isna(val):
                            dt = pd.to_datetime(val)
                            created_at = dt.to_pydatetime()
                    except (ValueError, TypeError):
                        pass 

                # Escribimos: survey_id, user_id (NULL), created_at, is_anonymous (True)
                survey_buffer.write(f"{survey.id}\t\\N\t{created_at.isoformat()}\tt\n")
            
            survey_buffer.seek(0)
            
            # Usamos pg_cursor (el crudo) para la carga rápida
            if hasattr(pg_cursor, 'copy_expert'):
                # psycopg2 API
                pg_cursor.copy_expert(
                    sql="""
                        COPY surveys_surveyresponse (survey_id, user_id, created_at, is_anonymous)
                        FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t', NULL '\\N')
                    """,
                    file=survey_buffer
                )
            elif hasattr(pg_cursor, 'copy'):
                # psycopg3 API: usar el context manager .copy(...) y escribir el contenido
                sql = """
                    COPY surveys_surveyresponse (survey_id, user_id, created_at, is_anonymous)
                    FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t', NULL '\\N')
                """
                with pg_cursor.copy(sql) as copy_obj:
                    copy_obj.write(survey_buffer.getvalue())
            else:
                raise Exception(
                    "Error de Driver: No se encontró el método 'copy_expert' ni 'copy'. "
                    "Asegúrate de estar usando un driver PostgreSQL compatible."
                )

            # Recuperar los IDs generados (Usamos el cursor de Django normal para consultas SELECT)
            django_cursor.execute("""
                SELECT id FROM surveys_surveyresponse 
                WHERE survey_id = %s 
                ORDER BY id DESC 
                LIMIT %s
            """, [survey.id, total_rows])
            
            survey_response_ids = [r[0] for r in django_cursor.fetchall()]
            survey_response_ids.reverse()

            # ---------------------------------------------------------
            # Paso 2: COPY para QuestionResponse
            # ---------------------------------------------------------
            answer_buffer = io.StringIO()
            answers_count = 0
            
            for idx, row in enumerate(rows):
                if idx >= len(survey_response_ids):
                    break
                    
                survey_response_id = survey_response_ids[idx]
                
                for column_name, value in row.items():
                    if column_name not in questions_map or pd.isna(value) or (isinstance(value, str) and not value.strip()):
                        continue
                    
                    question_data = questions_map[column_name]
                    question = question_data['question']
                    dtype = question_data['dtype']
                    
                    # --- Lógica de Tipos de Pregunta ---
                    
                    if dtype == 'single':
                        options = question_data.get('options', {})
                        option_obj_or_id = options.get(str(value).strip())
                        
                        if option_obj_or_id:
                            option_id = getattr(option_obj_or_id, 'id', option_obj_or_id)
                            answer_buffer.write(f"{survey_response_id}\t{question.id}\t{option_id}\t\\N\t\\N\n")
                            answers_count += 1

                    elif dtype == 'multi':
                        options = question_data.get('options', {})
                        for opt in str(value).split(','):
                            opt_clean = opt.strip()
                            if not opt_clean: 
                                continue
                                
                            option_obj_or_id = options.get(opt_clean)
                            if option_obj_or_id:
                                option_id = getattr(option_obj_or_id, 'id', option_obj_or_id)
                                answer_buffer.write(f"{survey_response_id}\t{question.id}\t{option_id}\t\\N\t\\N\n")
                                answers_count += 1

                    elif dtype in ['number', 'scale']:
                        try:
                            numeric_val = int(float(value))
                            answer_buffer.write(f"{survey_response_id}\t{question.id}\t\\N\t{numeric_val}\t\\N\n")
                            answers_count += 1
                        except (ValueError, TypeError):
                            continue

                    else:  # text
                        text_val = str(value)[:500].replace('\t', ' ').replace('\n', ' ').replace('\\', '\\\\')
                        answer_buffer.write(f"{survey_response_id}\t{question.id}\t\\N\t\\N\t{text_val}\n")
                        answers_count += 1

            # Ejecutar COPY final de respuestas
            answer_buffer.seek(0)
            if answers_count > 0:
                if hasattr(pg_cursor, 'copy_expert'):
                    pg_cursor.copy_expert(
                        sql="""
                            COPY surveys_questionresponse 
                            (survey_response_id, question_id, selected_option_id, numeric_value, text_value)
                            FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t', NULL '\\N')
                        """,
                        file=answer_buffer
                    )
                elif hasattr(pg_cursor, 'copy'):
                    sql2 = """
                        COPY surveys_questionresponse 
                        (survey_response_id, question_id, selected_option_id, numeric_value, text_value)
                        FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t', NULL '\\N')
                    """
                    with pg_cursor.copy(sql2) as copy_obj:
                        copy_obj.write(answer_buffer.getvalue())
                else:
                    raise Exception(
                        "Error de Driver: No se encontró el método 'copy_expert' ni 'copy'. "
                        "Asegúrate de estar usando un driver PostgreSQL compatible."
                    )

    return total_rows, answers_count
