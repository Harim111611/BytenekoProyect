"""
Fast CSV import command with signals disabled and bulk insert.
Optimized with pre-caching and double bulk create for 10k+ imports in <5 seconds.
"""
from django.core.management.base import BaseCommand
from django.db import transaction, connection
from surveys.signals import disable_signals, enable_signals
from surveys.models import Survey, Question, AnswerOption, SurveyResponse, QuestionResponse
from django.contrib.auth import get_user_model
import csv
import logging
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    """
    Import large CSV files with optimized bulk operations.
    
    Strategy:
    1. Pre-cache: Load all Questions and AnswerOptions into memory (O(1) lookup)
    2. Double Bulk Create: 
       - Bulk create SurveyResponse (get auto-generated IDs)
       - Use those IDs to build QuestionResponse objects
       - Bulk create QuestionResponse
    3. Memory management: Process in batches to avoid RAM overflow
    
    Usage:
        python manage.py import_csv_fast <file.csv> --survey-id=<id>
        
    CSV Format Expected:
        Header: question_1,question_2,question_3,...
        Rows: answer_value,answer_value,answer_value,...
    """
    
    help = 'Import CSV responses with signals disabled and bulk insert for maximum speed'
    
    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to CSV file')
        parser.add_argument('--survey-id', type=int, required=True, help='Survey ID')
        parser.add_argument('--user-id', type=int, required=False, help='User ID (optional)')
        parser.add_argument('--batch-size', type=int, default=1000, help='Batch size for bulk insert')
        parser.add_argument('--skip-header', action='store_true', help='Skip first row (if not using DictReader)')
        parser.add_argument('--optimize-postgres', action='store_true', help='Enable PostgreSQL optimizations (faster imports)')
    
    def handle(self, *args, **options):
        csv_file = options['csv_file']
        survey_id = options['survey_id']
        user_id = options.get('user_id')
        batch_size = options['batch_size']
        
        try:
            survey = Survey.objects.get(id=survey_id)
        except Survey.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'Survey {survey_id} does not exist'))
            return
        
        user = None
        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                self.stderr.write(self.style.WARNING(f'User {user_id} not found, importing as anonymous'))
        
        self.stdout.write(f'Starting CSV import for survey "{survey.title}"...')
        self.stdout.write(f'Batch size: {batch_size}')
        
        # STEP 1: Pre-cache all questions and options (O(1) memory lookup)
        self.stdout.write('Pre-caching questions and options...')
        questions_cache = self._build_questions_cache(survey)
        self.stdout.write(f'Cached {len(questions_cache)} questions')
        
        # Disable signals for maximum performance
        disable_signals()
        
        # Apply PostgreSQL optimizations if requested
        if options.get('optimize_postgres', False):
            self._apply_postgres_optimizations()
        
        start_time = datetime.now()
        total_survey_responses = 0
        total_question_responses = 0
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                survey_responses_batch = []
                csv_rows_batch = []  # Keep CSV data for later processing
                
                for row_num, row in enumerate(reader, start=1):
                    # Create SurveyResponse object (not saved yet)
                    survey_response = SurveyResponse(
                        survey=survey,
                        user=None,
                        is_anonymous=True
                    )
                    survey_responses_batch.append(survey_response)
                    csv_rows_batch.append(row)
                    
                    # STEP 2: Bulk insert when batch is full
                    if len(survey_responses_batch) >= batch_size:
                        qr_count = self._process_batch(
                            survey_responses_batch, 
                            csv_rows_batch, 
                            questions_cache,
                            survey
                        )
                        total_survey_responses += len(survey_responses_batch)
                        total_question_responses += qr_count
                        
                        self.stdout.write(
                            f'Imported {total_survey_responses} survey responses, '
                            f'{total_question_responses} question responses...',
                            ending='\r'
                        )
                        
                        # Clear batches to free memory
                        survey_responses_batch = []
                        csv_rows_batch = []
                
                # Process remaining batch
                if survey_responses_batch:
                    qr_count = self._process_batch(
                        survey_responses_batch, 
                        csv_rows_batch, 
                        questions_cache,
                        survey
                    )
                    total_survey_responses += len(survey_responses_batch)
                    total_question_responses += qr_count
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            self.stdout.write(self.style.SUCCESS(
                f'\n[SUCCESS] Imported in {duration:.2f}s:'
            ))
            self.stdout.write(f'   - {total_survey_responses} survey responses')
            self.stdout.write(f'   - {total_question_responses} question responses')
            self.stdout.write(f'   - Time: {duration:.2f} seconds')
            self.stdout.write(f'   - Speed: {total_survey_responses/duration:.0f} surveys/sec')
            if total_question_responses > 0:
                self.stdout.write(f'   - Speed: {total_question_responses/duration:.0f} answers/sec')
            
        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f'File not found: {csv_file}'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error during import: {str(e)}'))
            import traceback
            traceback.print_exc()
            raise
        finally:
            enable_signals()
            self.stdout.write('Signals re-enabled')
    
    def _build_questions_cache(self, survey):
        """
        Pre-cache all questions and their answer options.
        Returns: {
            'question_text_or_order': {
                'question': Question object,
                'options': {option_text: AnswerOption object}
            }
        }
        Complexity: O(N) once, then O(1) lookups
        """
        cache = {}
        questions = Question.objects.filter(survey=survey).prefetch_related('options')
        
        for question in questions:
            # Cache by both order and text for flexibility
            question_data = {
                'question': question,
                'options': {}
            }
            
            # Cache answer options for multiple choice questions
            for option in question.options.all():
                question_data['options'][option.text.strip().lower()] = option
            
            # Cache by order (e.g., "question_1", "q1", or just "1")
            cache[f'question_{question.order}'] = question_data
            cache[f'q{question.order}'] = question_data
            cache[str(question.order)] = question_data
            
            # Also cache by question text (normalized)
            cache[question.text.strip().lower()] = question_data
        
        return cache
    
    def _process_batch(self, survey_responses_batch, csv_rows_batch, questions_cache, survey):
        """
        Double bulk create:
        1. Bulk create SurveyResponse (get IDs from DB)
        2. Build QuestionResponse objects using those IDs
        3. Bulk create QuestionResponse
        
        Returns: Number of QuestionResponse objects created
        """
        with transaction.atomic():
            # STEP 1: Bulk create SurveyResponse and get IDs
            # PostgreSQL returns IDs automatically
            created_responses = SurveyResponse.objects.bulk_create(survey_responses_batch)
            
            # STEP 2: Build QuestionResponse objects using the IDs
            question_responses = []
            
            for i, (survey_response, csv_row) in enumerate(zip(created_responses, csv_rows_batch)):
                # Process each column in the CSV row
                for column_name, answer_value in csv_row.items():
                    if not answer_value or column_name in ['ip_address', 'user_agent']:
                        continue  # Skip empty answers and metadata columns
                    
                    # Normalize column name for cache lookup
                    normalized_col = column_name.strip().lower()
                    
                    # Try to find question in cache
                    question_data = None
                    for key_variant in [normalized_col, f'question_{normalized_col}', f'q{normalized_col}']:
                        if key_variant in questions_cache:
                            question_data = questions_cache[key_variant]
                            break
                    
                    if not question_data:
                        logger.warning(f'Question not found for column: {column_name}')
                        continue
                    
                    question = question_data['question']
                    
                    # Build QuestionResponse
                    qr = QuestionResponse(
                        survey_response=survey_response,
                        question=question
                    )
                    
                    # Handle different question types
                    if question.type == 'single':
                        # Find matching option
                        normalized_answer = answer_value.strip().lower()
                        option = question_data['options'].get(normalized_answer)
                        if option:
                            qr.selected_option = option
                        else:
                            # If option not found, store as text
                            qr.text_value = answer_value
                    
                    elif question.type == 'scale':
                        try:
                            qr.numeric_value = int(answer_value)
                        except ValueError:
                            qr.text_value = answer_value
                    
                    else:  # text, textarea
                        qr.text_value = answer_value
                    
                    question_responses.append(qr)
            
            # STEP 3: Bulk create all QuestionResponse objects
            # Use larger batch size for PostgreSQL (can handle 10k+ efficiently)
            if question_responses:
                QuestionResponse.objects.bulk_create(question_responses, batch_size=10000)
            
            return len(question_responses)
    
    def _apply_postgres_optimizations(self):
        """
        Apply PostgreSQL-specific optimizations for bulk imports.
        
        Based on PostgreSQL best practices for bulk loading:
        https://www.postgresql.org/docs/current/populate.html
        
        These settings improve write performance significantly by:
        - Increasing work memory for sorting/indexing
        - Disabling synchronous commit (trades immediate durability for speed)
        - Increasing maintenance work memory for bulk operations
        
        NOTE: synchronous_commit=OFF means data is written to OS but not
        immediately fsynced to disk. Data is still durable but with a small
        window of potential loss on system crash.
        """
        with connection.cursor() as cursor:
            # Increase work memory for this session (helps with sorting/indexing)
            cursor.execute("SET work_mem = '256MB';")
            
            # Disable synchronous commit for this session (trades durability for speed)
            # Data is still written but not immediately fsynced to disk
            cursor.execute("SET synchronous_commit = OFF;")
            
            # Increase maintenance work memory (helps with bulk operations)
            cursor.execute("SET maintenance_work_mem = '256MB';")
            
            # Use faster checksum algorithm if available
            cursor.execute("SET wal_compression = ON;")
            
        self.stdout.write(self.style.WARNING(
            'PostgreSQL optimizations applied:\n'
            '  - work_mem: 256MB\n'
            '  - synchronous_commit: OFF\n'
            '  - maintenance_work_mem: 256MB\n'
            '  - wal_compression: ON'
        ))
        logger.info('PostgreSQL session optimizations applied for bulk import')
