"""
Utilidades de importación masiva usando PostgreSQL COPY FROM.
Alto rendimiento para insertar grandes volúmenes de datos.
Soporta psycopg2 (copy_expert) y psycopg 3 (copy).
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

    print(f"DEBUG: Iniciando importación de {total_rows} filas para encuesta {survey.id}")

    with transaction.atomic():
        with connection.cursor() as django_cursor:
            # ---------------------------------------------------------
            # 1. Obtener el cursor real (Driver específico)
            # ---------------------------------------------------------
            pg_cursor = django_cursor.cursor
            
            # Desempaquetar capas (como Django Debug Toolbar)
            while hasattr(pg_cursor, 'cursor'):
                pg_cursor = pg_cursor.cursor
            
            print(f"DEBUG: Tipo de cursor detectado: {type(pg_cursor)}")
            
            # Detectar capacidades del driver
            use_psycopg2 = hasattr(pg_cursor, 'copy_expert')
            use_psycopg3 = hasattr(pg_cursor, 'copy')

            if not (use_psycopg2 or use_psycopg3):
                # Fallback: Intentar acceder a .connection.cursor() si es un wrapper extraño
                try:
                    pg_cursor = django_cursor.connection.cursor()
                    use_psycopg2 = hasattr(pg_cursor, 'copy_expert')
                    use_psycopg3 = hasattr(pg_cursor, 'copy')
                    print(f"DEBUG: Re-intento con cursor de conexión: {type(pg_cursor)}")
                except:
                    pass

            if not (use_psycopg2 or use_psycopg3):
                raise Exception(
                    f"Error de Driver: El cursor {type(pg_cursor)} no soporta COPY. "
                    "Asegúrate de usar PostgreSQL en settings.local."
                )

            # ---------------------------------------------------------
            # 2. Preparar Buffer para SurveyResponse
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

                # Formato: survey_id, user_id, created_at, is_anonymous
                # Postgres COPY usa \N para NULL y \t como delimitador por defecto
                survey_buffer.write(f"{survey.id}\t\\N\t{created_at.isoformat()}\tt\n")
            
            survey_buffer.seek(0)
            
            # ---------------------------------------------------------
            # 3. Ejecutar COPY (SurveyResponse)
            # ---------------------------------------------------------
            sql_survey = """
                COPY surveys_surveyresponse (survey_id, user_id, created_at, is_anonymous)
                FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t', NULL '\\N')
            """

            if use_psycopg2:
                pg_cursor.copy_expert(sql=sql_survey, file=survey_buffer)
            else: # psycopg3
                with pg_cursor.copy(sql_survey) as copy:
                    copy.write(survey_buffer.getvalue())

            # ---------------------------------------------------------
            # 4. Recuperar IDs generados
            # ---------------------------------------------------------
            # Importante: Usamos el cursor de Django estándar para consultas normales
            django_cursor.execute("""
                SELECT id FROM surveys_surveyresponse 
                WHERE survey_id = %s 
                ORDER BY id DESC 
                LIMIT %s
            """, [survey.id, total_rows])
            
            # Los IDs vienen en orden descendente (últimos insertados), invertimos para alinear con filas
            survey_response_ids = [r[0] for r in django_cursor.fetchall()]
            survey_response_ids.reverse()

            # ---------------------------------------------------------
            # 5. Preparar Buffer para QuestionResponse
            # ---------------------------------------------------------
            answer_buffer = io.StringIO()
            answers_count = 0
            
            for idx, row in enumerate(rows):
                if idx >= len(survey_response_ids):
                    break
                    
                survey_response_id = survey_response_ids[idx]
                
                for column_name, value in row.items():
                    # Ignorar columnas no mapeadas o valores vacíos
                    if column_name not in questions_map or pd.isna(value):
                        continue
                    if isinstance(value, str) and not value.strip():
                        continue
                    
                    question_data = questions_map[column_name]
                    question = question_data['question']
                    dtype = question_data['dtype']
                    
                    # --- Lógica de Tipos de Pregunta ---
                    
                    if dtype == 'single':
                        options = question_data.get('options', {})
                        val_str = str(value).strip()
                        option_obj = options.get(val_str)
                        
                        if option_obj:
                            opt_id = getattr(option_obj, 'id', option_obj)
                            answer_buffer.write(f"{survey_response_id}\t{question.id}\t{opt_id}\t\\N\t\\N\n")
                            answers_count += 1

                    elif dtype == 'multi':
                        options = question_data.get('options', {})
                        for part in str(value).split(','):
                            part_clean = part.strip()
                            if not part_clean: continue
                            
                            option_obj = options.get(part_clean)
                            if option_obj:
                                opt_id = getattr(option_obj, 'id', option_obj)
                                answer_buffer.write(f"{survey_response_id}\t{question.id}\t{opt_id}\t\\N\t\\N\n")
                                answers_count += 1

                    elif dtype in ['number', 'scale']:
                        try:
                            num_val = int(float(value))
                            answer_buffer.write(f"{survey_response_id}\t{question.id}\t\\N\t{num_val}\t\\N\n")
                            answers_count += 1
                        except:
                            pass

                    else: # text
                        text_val = str(value)[:500].replace('\t', ' ').replace('\n', ' ').replace('\\', '\\\\')
                        answer_buffer.write(f"{survey_response_id}\t{question.id}\t\\N\t\\N\t{text_val}\n")
                        answers_count += 1

            # ---------------------------------------------------------
            # 6. Ejecutar COPY (QuestionResponse)
            # ---------------------------------------------------------
            if answers_count > 0:
                answer_buffer.seek(0)
                sql_answers = """
                    COPY surveys_questionresponse 
                    (survey_response_id, question_id, selected_option_id, numeric_value, text_value)
                    FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t', NULL '\\N')
                """
                
                if use_psycopg2:
                    pg_cursor.copy_expert(sql=sql_answers, file=answer_buffer)
                else:
                    with pg_cursor.copy(sql_answers) as copy:
                        copy.write(answer_buffer.getvalue())

    return total_rows, answers_count
