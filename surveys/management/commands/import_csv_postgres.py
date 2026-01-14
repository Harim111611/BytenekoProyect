"""
Comando optimizado para importar CSV usando COPY FROM de PostgreSQL.
Bypassing Django ORM para máximo rendimiento.

Performance esperado: <3 segundos para 10k surveys (100k answers)
"""
import csv
import io
import time
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from surveys.models import Survey


class Command(BaseCommand):
    help = 'Importa respuestas de CSV usando PostgreSQL COPY FROM (ultra rápido)'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Ruta al archivo CSV')
        parser.add_argument('--survey-id', type=int, required=True, help='ID de la encuesta')

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        survey_id = options['survey_id']
        
        start_time = time.time()
        
        # Validar que existe la encuesta
        try:
            survey = Survey.objects.get(id=survey_id)
        except Survey.DoesNotExist as err:
            raise CommandError(f'Survey con ID {survey_id} no existe') from err
        
        self.stdout.write(f'Importando CSV para encuesta: {survey.title}')
        
        # Construir caché de questions
        questions_cache = self._build_questions_cache(survey)
        self.stdout.write(f'Cache construido: {len(questions_cache)} columnas')
        
        # Leer CSV y preparar datos
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        total_rows = len(rows)
        self.stdout.write(f'Procesando {total_rows} respuestas...')
        
        # Importar usando COPY FROM
        surveys_created, answers_created = self._import_with_copy(
            rows, survey_id, questions_cache
        )
        
        duration = time.time() - start_time
        
        self.stdout.write(self.style.SUCCESS(
            f'Importacion completada en {duration:.2f}s\n'
            f'   - {surveys_created} SurveyResponse creados\n'
            f'   - {answers_created} QuestionResponse creados\n'
            f'   - Velocidad: {surveys_created/duration:.0f} surveys/seg, '
            f'{answers_created/duration:.0f} answers/seg'
        ))

    def _build_questions_cache(self, survey):
        """Pre-carga todas las preguntas y opciones en memoria"""
        from surveys.models import Question, AnswerOption
        
        cache = {}
        questions = Question.objects.filter(survey=survey).prefetch_related('options')
        
        for idx, question in enumerate(questions, 1):
            column_name = f'question_{idx}'
            
            # Solo cachear preguntas con opciones
            options_list = list(question.options.all())
            if not options_list:
                continue
                
            options_dict = {
                opt.text: opt.id 
                for opt in options_list
            }
            cache[column_name] = {
                'question_id': question.id,
                'options': options_dict
            }
        
        return cache

    def _import_with_copy(self, rows, survey_id, questions_cache):
        """Importa datos usando PostgreSQL COPY FROM"""
        from datetime import datetime
        
        with transaction.atomic():
            with connection.cursor() as cursor:
                # Paso 1: COPY para SurveyResponse
                survey_buffer = io.StringIO()
                
                for row in rows:
                    # Format: survey_id, user_id, created_at, is_anonymous
                    # PostgreSQL espera formato: survey_id\tuser_id\tcreated_at\tis_anonymous
                    survey_buffer.write(f"{survey_id}\t\\N\t{datetime.now().isoformat()}\tf\n")
                
                survey_buffer.seek(0)
                
                # Ejecutar COPY FROM para SurveyResponse
                cursor.copy_expert(
                    sql="""
                        COPY surveys_surveyresponse (survey_id, user_id, created_at, is_anonymous)
                        FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t', NULL '\\N')
                    """,
                    file=survey_buffer
                )
                
                surveys_created = len(rows)
                
                # Obtener los IDs generados (últimos N registros)
                cursor.execute("""
                    SELECT id FROM surveys_surveyresponse 
                    WHERE survey_id = %s 
                    ORDER BY id DESC 
                    LIMIT %s
                """, [survey_id, surveys_created])
                
                survey_response_ids = [row[0] for row in cursor.fetchall()]
                survey_response_ids.reverse()  # Orden correcto
                
                # Paso 2: COPY para QuestionResponse
                answer_buffer = io.StringIO()
                answers_count = 0
                
                self.stdout.write(f'Procesando {len(rows)} rows con {len(survey_response_ids)} IDs')
                
                for idx, row in enumerate(rows):
                    survey_response_id = survey_response_ids[idx]
                    
                    for column_name, value in row.items():
                        # Skip empty/null values
                        if not value or (isinstance(value, str) and not value.strip()):
                            continue
                        
                        # Skip ONLY technical/system metadata columns
                        # Permiten fechas, IDs, usuarios, comentarios para historial
                        skip_completely_keywords = [
                            'ip_address', 'user_agent', 'navigator'
                        ]
                        
                        col_lower = column_name.strip().lower()
                        if any(kw in col_lower for kw in skip_completely_keywords):
                            continue  # Skip only these technical columns
                        
                        # Try to find question in cache with multiple matching strategies
                        question_data = None
                        
                        if column_name in questions_cache:
                            question_data = questions_cache[column_name]
                        else:
                            # Extract numeric order from column name and try matching
                            import re
                            numeric_match = re.search(r'(\d+)', column_name.lower())
                            numeric_order = numeric_match.group(1) if numeric_match else None
                            
                            if numeric_order:
                                for key_variant in [f'question_{numeric_order}', numeric_order]:
                                    if key_variant in questions_cache:
                                        question_data = questions_cache[key_variant]
                                        break
                        
                        if not question_data:
                            continue
                        question_id = question_data['question_id']
                        
                        # Buscar option_id
                        option_id = question_data['options'].get(value)
                        if not option_id:
                            continue
                        
                        # Format: survey_response_id, question_id, selected_option_id
                        answer_buffer.write(
                            f"{survey_response_id}\t{question_id}\t{option_id}\n"
                        )
                        answers_count += 1
                
                self.stdout.write(f'Buffer construido con {answers_count} respuestas')
                answer_buffer.seek(0)
                
                # Ejecutar COPY FROM para QuestionResponse
                cursor.copy_expert(
                    sql="""
                        COPY surveys_questionresponse 
                        (survey_response_id, question_id, selected_option_id)
                        FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t')
                    """,
                    file=answer_buffer
                )
        
        return surveys_created, answers_count
