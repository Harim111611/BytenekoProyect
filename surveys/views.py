# surveys/views.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, CreateView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib import messages
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from django.db import transaction, connection
from django_ratelimit.decorators import ratelimit
import json
import pandas as pd
import logging
from datetime import datetime

from .models import Survey, Question, AnswerOption, SurveyResponse, QuestionResponse
from .signals import DisableSignals
from surveys.utils.bulk_import import bulk_import_responses_postgres
from core.validators import CSVImportValidator, ResponseValidator
from core.mixins import OwnerRequiredMixin, EncuestaQuerysetMixin
from core.utils.helpers import PermissionHelper
from core.utils.logging_utils import (
    StructuredLogger,
    log_performance,
    log_user_action,
    log_data_change,
    log_security_event
)

# Configurar logger
logger = StructuredLogger('surveys')


# ============================================================
# VISTAS CRUD (Limpias, la caché se maneja por señales)
# ============================================================

class EncuestaListView(LoginRequiredMixin, EncuestaQuerysetMixin, ListView):
    """Vista lista de encuestas del usuario actual."""
    model = Survey
    template_name = 'surveys/list.html'
    context_object_name = 'surveys'


class EncuestaDetailView(LoginRequiredMixin, OwnerRequiredMixin, DetailView):
    """Vista detalle de encuesta (solo creador)."""
    model = Survey
    template_name = 'surveys/detail.html'
    context_object_name = 'survey'


class EncuestaCreateView(LoginRequiredMixin, CreateView):
    """Vista para crear nueva encuesta."""
    model = Survey
    template_name = 'surveys/survey_create.html'
    fields = ['title', 'description', 'status', 'category']
    success_url = reverse_lazy('surveys:list')

    def post(self, request, *args, **kwargs):
        # Manejo de creación vía AJAX (JSON)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                survey = Survey.objects.create(
                    author=request.user,
                    title=data['surveyInfo'].get('title', data['surveyInfo'].get('titulo', '')),
                    description=data['surveyInfo'].get('description', data['surveyInfo'].get('descripcion', '')),
                    category=data['surveyInfo'].get('category', data['surveyInfo'].get('categoria', 'General')),
                    status='draft'
                )

                for i, q in enumerate(data['questions']):
                    question_type = {'text': 'text', 'number': 'number', 'scale': 'scale', 'single': 'single',
                            'multi': 'multi'}.get(q.get('type', q.get('tipo')), 'text')
                    question = Question.objects.create(survey=survey, text=q.get('text', q.get('titulo', '')), type=question_type, order=i,
                                                is_required=q.get('required', False))
                    if q.get('options', q.get('opciones')):
                        for opt in q.get('options', q.get('opciones', [])):
                            AnswerOption.objects.create(question=question, text=opt)

                log_user_action(
                    'create_survey',
                    success=True,
                    user_id=request.user.id,
                    survey_title=survey.title,
                    category=survey.category
                )

                return JsonResponse(
                    {'success': True, 'redirect_url': str(reverse_lazy('surveys:detail', kwargs={'pk': survey.pk}))})
            except Exception as e:
                logger.exception(f"Error al crear encuesta vía AJAX: {e}")
                return JsonResponse({'error': str(e)}, status=500)
        
        # Si no es AJAX, usar el flujo normal del formulario
        return super().post(request, *args, **kwargs)
    
    def form_valid(self, form):
        """Asigna el creador antes de guardar."""
        form.instance.author = self.request.user
        
        # Log data change
        log_user_action(
            'create_survey',
            success=True,
            user_id=self.request.user.id,
            survey_title=form.instance.title,
            category=form.instance.category
        )
        
        return super().form_valid(form)


class EncuestaUpdateView(LoginRequiredMixin, OwnerRequiredMixin, UpdateView):
    """Vista para actualizar encuesta (solo creador)."""
    model = Survey
    fields = ['title', 'description', 'status']
    template_name = 'surveys/form.html'
    success_url = reverse_lazy('surveys:list')


class EncuestaDeleteView(LoginRequiredMixin, OwnerRequiredMixin, DeleteView):
    """Vista para eliminar encuesta (solo creador)."""
    model = Survey
    template_name = 'surveys/confirm_delete.html'
    success_url = reverse_lazy('surveys:list')
    
    def post(self, request, *args, **kwargs):
        """Sobrescribe POST para usar SQL crudo en vez de ORM delete()."""
        return self.delete(request, *args, **kwargs)
    
    def delete(self, request, *args, **kwargs):
        """Eliminación ultra-rápida usando SQL crudo (bypassing ORM)."""
        from django.core.cache import cache
        from surveys.signals import disable_signals, enable_signals
        from django.db import connection
        
        # CRÍTICO: deshabilitar signals ANTES de get_object()
        disable_signals()
        
        survey = self.get_object()
        survey_id = survey.id
        author_id = survey.author.id if survey.author else None
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # SQL crudo con parámetros (seguro contra SQL injection)
                    # Orden correcto de dependencias para evitar FK errors
                    
                    # 1. QuestionResponse (tabla más pesada)
                    cursor.execute("""
                        DELETE FROM surveys_questionresponse 
                        WHERE survey_response_id IN (
                            SELECT id FROM surveys_surveyresponse WHERE survey_id = %s
                        )
                    """, [survey_id])
                    
                    # 2. SurveyResponse
                    cursor.execute("""
                        DELETE FROM surveys_surveyresponse WHERE survey_id = %s
                    """, [survey_id])
                    
                    # 3. AnswerOption
                    cursor.execute("""
                        DELETE FROM surveys_answeroption 
                        WHERE question_id IN (
                            SELECT id FROM surveys_question WHERE survey_id = %s
                        )
                    """, [survey_id])
                    
                    # 4. Question
                    cursor.execute("""
                        DELETE FROM surveys_question WHERE survey_id = %s
                    """, [survey_id])
                    
                    # 5. Survey (raíz)
                    cursor.execute("""
                        DELETE FROM surveys_survey WHERE id = %s
                    """, [survey_id])
                    
        except Exception as e:
            logger.error(f"Error eliminando encuesta {survey_id}: {e}")
            messages.error(request, "Error al eliminar la encuesta.")
            return redirect(self.success_url)
        finally:
            enable_signals()
        
        # Invalidar caché una sola vez
        if author_id:
            cache.delete(f"dashboard_data_user_{author_id}")
            try:
                cache.delete_pattern(f"survey_*{survey_id}*")
            except:
                pass
        
        messages.success(request, 'Encuesta eliminada correctamente.')
        return redirect(self.success_url)


@login_required
@require_POST
def bulk_delete_surveys_view(request):
    """Eliminación bulk ultra-rápida usando SQL crudo."""
    from django.core.cache import cache
    from surveys.signals import disable_signals, enable_signals
    from django.db import connection
    
    survey_ids = request.POST.getlist('survey_ids')
    
    if not survey_ids:
        messages.error(request, 'No se seleccionaron encuestas para eliminar.')
        return redirect('surveys:list')
    
    # Validar propiedad y sanitizar IDs
    try:
        clean_ids = [int(sid) for sid in survey_ids]
    except ValueError:
        messages.error(request, 'IDs inválidos.')
        return redirect('surveys:list')
    
    # CRÍTICO: deshabilitar signals ANTES de cualquier ORM query
    disable_signals()
    
    # Verificar que pertenecen al usuario
    owned_ids = list(Survey.objects.filter(
        id__in=clean_ids,
        author=request.user
    ).values_list('id', flat=True))
    
    if not owned_ids:
        enable_signals()  # Re-habilitar antes de return
        messages.error(request, 'No tienes permisos para eliminar las encuestas seleccionadas.')
        return redirect('surveys:list')
    
    count = len(owned_ids)
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # Usar PostgreSQL ANY() para pasar array de forma segura
                # 1. QuestionResponse
                cursor.execute("""
                    DELETE FROM surveys_questionresponse 
                    WHERE survey_response_id IN (
                        SELECT id FROM surveys_surveyresponse 
                        WHERE survey_id = ANY(%s)
                    )
                """, [owned_ids])
                
                # 2. SurveyResponse
                cursor.execute("""
                    DELETE FROM surveys_surveyresponse 
                    WHERE survey_id = ANY(%s)
                """, [owned_ids])
                
                # 3. AnswerOption
                cursor.execute("""
                    DELETE FROM surveys_answeroption 
                    WHERE question_id IN (
                        SELECT id FROM surveys_question 
                        WHERE survey_id = ANY(%s)
                    )
                """, [owned_ids])
                
                # 4. Question
                cursor.execute("""
                    DELETE FROM surveys_question 
                    WHERE survey_id = ANY(%s)
                """, [owned_ids])
                
                # 5. Survey
                cursor.execute("""
                    DELETE FROM surveys_survey 
                    WHERE id = ANY(%s)
                """, [owned_ids])
                
    except Exception as e:
        logger.error(f"Error en bulk delete: {e}")
        messages.error(request, f"Error eliminando encuestas.")
        return redirect('surveys:list')
    finally:
        enable_signals()
    
    # Invalidar caché
    cache.delete(f"dashboard_data_user_{request.user.id}")
    
    # Mensaje de éxito
    if count == 1:
        messages.success(request, 'Se eliminó 1 encuesta correctamente.')
    else:
        messages.success(request, f'Se eliminaron {count} encuestas correctamente.')
    
    return redirect('surveys:list')


# ============================================================
# FUNCIONES ADICIONALES
# ============================================================

@login_required
@ratelimit(key='user', rate='5/h', method='POST', block=True)
@log_performance(threshold_ms=5000)
def import_survey_view(request):
    """
    Importación CSV optimizada con PostgreSQL COPY FROM.
    
    Performance: ~3.4s para 10k filas, ~40k respuestas.
    
    TODO (Producción): Para archivos >50k filas, migrar a Celery para evitar timeouts HTTP:
    - Crear task en surveys/tasks.py: @shared_task def import_csv_async(file_path, user_id)
    - Retornar task_id al usuario y mostrar progreso con polling/WebSockets
    - Notificar por email cuando termine
    
    Límites actuales:
    - Timeout HTTP: 30-60s (Nginx/Gunicorn)
    - Max filas: 100k (configurable)
    - Max tamaño: 50MB
    """
    # Límites de seguridad para producción
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
    MAX_ROWS = 100000  # 100k filas
    MAX_COLUMNS = 500  # 500 columnas
    TIMEOUT_WARNING_ROWS = 50000  # Advertencia para archivos grandes que podrían causar timeout HTTP
    
    if request.method == 'POST' and request.FILES.get('csv_file'):
        try:
            # Validar tamaño del archivo antes de procesarlo
            csv_file = request.FILES.get('csv_file')
            if csv_file.size > MAX_FILE_SIZE:
                raise ValidationError(
                    f'El archivo excede el tamaño máximo permitido de {MAX_FILE_SIZE // (1024*1024)} MB. '
                    f'Tamaño del archivo: {csv_file.size / (1024*1024):.2f} MB'
                )
            
            # Validar archivo CSV
            csv_file = CSVImportValidator.validate_csv_file(csv_file)
            
            # Log inicio de importación
            log_user_action(
                'start_csv_import',
                success=True,
                user_id=request.user.id,
                filename=csv_file.name
            )
            
            # Leer y validar DataFrame con detección automática de codificación
            try:
                # Intentar varias codificaciones comunes
                encodings = [
                    'utf-8-sig',  # UTF-8 con BOM
                    'utf-8',
                    'utf-16',  # UTF-16 con BOM
                    'utf-16-le',  # UTF-16 Little Endian
                    'utf-16-be',  # UTF-16 Big Endian
                    'latin-1',
                    'iso-8859-1',
                    'cp1252',
                    'windows-1252',
                    'mac_roman'
                ]
                df = None
                last_error = None
                
                for encoding in encodings:
                    try:
                        csv_file.seek(0)  # Resetear posición del archivo
                        # Leer con límites de filas para evitar consumo excesivo de memoria
                        df = pd.read_csv(
                            csv_file, 
                            encoding=encoding,
                            nrows=MAX_ROWS + 1  # +1 para detectar si excede el límite
                        )
                        logger.info(f"CSV importado exitosamente con codificación: {encoding}")
                        break
                    except (UnicodeDecodeError, UnicodeError) as e:
                        last_error = e
                        continue
                    except Exception as e:
                        # Otros errores pueden indicar que la codificación funcionó pero hay otro problema
                        # Intentar la siguiente codificación
                        last_error = e
                        continue
                
                if df is None:
                    raise ValidationError(f'No se pudo leer el archivo. Asegúrate de que sea un archivo CSV válido. Intenta abrirlo en Excel y guardarlo como CSV UTF-8.')
                    
            except ValidationError:
                raise
            except Exception as e:
                raise ValidationError(f"Error al leer el archivo CSV: {str(e)}")
            
            # Validar límites de filas y columnas
            if len(df) > MAX_ROWS:
                raise ValidationError(
                    f'El archivo excede el límite de {MAX_ROWS:,} filas. '
                    f'Filas encontradas: {len(df):,}. '
                    f'Por favor, divide el archivo en partes más pequeñas.'
                )
            
            # Advertencia para archivos grandes que podrían causar timeout HTTP
            if len(df) > TIMEOUT_WARNING_ROWS:
                logger.warning(
                    f"Archivo grande detectado: {len(df):,} filas. "
                    f"Considerar usar tarea en segundo plano (Celery) para archivos >50k filas. "
                    f"Timeout HTTP típico: 30-60s. Usuario: {request.user.id}"
                )
            
            if len(df.columns) > MAX_COLUMNS:
                raise ValidationError(
                    f'El archivo excede el límite de {MAX_COLUMNS} columnas. '
                    f'Columnas encontradas: {len(df.columns)}'
                )
            
            df = CSVImportValidator.validate_dataframe(df)

            title = request.POST.get('survey_title', '').strip()
            if not title:
                title = f"Importada {csv_file.name}"
            elif len(title) > 255:
                raise ValidationError("El título de la encuesta no puede superar los 255 caracteres")

            with transaction.atomic():
                survey = Survey.objects.create(
                    author=request.user,
                    title=title,
                    description=f"Importada {datetime.now().strftime('%Y-%m-%d')}",
                    status='active',
                    sample_goal=len(df)
                )
                
                logger.info(f"Iniciando importación CSV: {len(df)} filas, {len(df.columns)} columnas para usuario {request.user.id}")

                # Mantenemos la lógica existente de detección de columnas
                col_map = {}
                date_col_name = None
                for i, col in enumerate(df.columns):
                    # Validar nombre de columna
                    col = CSVImportValidator.validate_column_name(col)
                    
                    # Excluir columnas de ID, timestamps y metadata
                    col_lower = col.lower()
                    skip_patterns = [
                        'response_id', 'respuesta_id', 'id_respuesta',
                        'timestamp', 'creado', 'created_at', 'updated_at'
                    ]
                    
                    # Patrones para identificadores y nombres personales
                    identity_patterns = [
                        'nombre', 'name', 'apellido', 'cliente', 'estudiante', 
                        'empleado', 'paciente', 'huesped', 'usuario', 'user',
                        'email', 'correo', 'telefono', 'phone', 'dni', 'cedula',
                        'identificacion', 'documento', 'reserva_id', 'empleado_id',
                        'paciente_id', 'cliente_id'
                    ]
                    
                    # Verificar si es columna de timestamp/fecha
                    if not date_col_name and any(x in col_lower for x in ['fecha', 'date', 'timestamp', 'time', 'creado']):
                        # Validar que la columna tenga fechas válidas (no todo NaT)
                        try:
                            date_series = pd.to_datetime(df[col], errors='coerce')
                            valid_dates = date_series.notna().sum()
                            total_dates = len(date_series)
                            
                            # Requerir al menos 50% de fechas válidas para considerarla columna de fecha
                            if valid_dates / total_dates >= 0.5:
                                date_col_name = col
                                col_map[col] = 'TIMESTAMP'
                                logger.info(f"Columna de fecha detectada: {col} ({valid_dates}/{total_dates} válidas)")
                            else:
                                logger.warning(
                                    f"Columna '{col}' parece fecha pero tiene {valid_dates}/{total_dates} valores válidos. "
                                    f"Tratándola como texto."
                                )
                        except Exception as e:
                            logger.error(f"Error validando columna de fecha '{col}': {e}")
                        continue
                    
                    # Saltar solo IDs exactos o de respuesta
                    if col_lower == 'id' or any(pattern in col_lower for pattern in skip_patterns):
                        logger.info(f"Saltando columna de metadata: {col}")
                        continue
                    
                    # Saltar columnas de identificación personal
                    if any(pattern in col_lower for pattern in identity_patterns):
                        logger.info(f"Saltando columna de identificación personal: {col}")
                        continue

                    # Crear preguntas basadas en el CSV
                    sample = df[col].dropna()
                    dtype = 'text'
                    if pd.api.types.is_numeric_dtype(sample):
                        dtype = 'scale' if sample.min() >= 0 and sample.max() <= 10 else 'number'
                    elif not sample.empty:
                        if sample.astype(str).str.contains(',').any():
                            dtype = 'multi'
                        elif sample.nunique() < 15:
                            dtype = 'single'

                    question = Question(survey=survey, text=col.replace('_', ' ').title(),
                                       type=dtype, order=i)
                    col_map[col] = {'question': question, 'dtype': dtype, 'unique_ops': set()}

                    # Recolectar opciones únicas sin crear aún
                    if dtype in ['single', 'multi']:
                        unique_ops = set()
                        for val in sample:
                            if pd.isna(val): continue
                            if dtype == 'single':
                                unique_ops.add(str(val)[:255])
                            else:
                                unique_ops.update([x.strip()[:255] for x in str(val).split(',')])
                        col_map[col]['unique_ops'] = unique_ops

                # OPTIMIZACIÓN CRÍTICA: Bulk create de todas las preguntas (N queries → 1 query)
                questions_to_create = [col_data['question'] for col, col_data in col_map.items() if col_data != 'TIMESTAMP']
                Question.objects.bulk_create(questions_to_create)
                
                # Actualizar col_map con las preguntas creadas (tienen IDs ahora)
                questions_created = list(
                    survey.questions.prefetch_related('options')
                    .all()
                    .order_by('order')
                )
                new_col_map = {}
                col_idx = 0
                for col, col_data in col_map.items():
                    if col_data == 'TIMESTAMP':
                        new_col_map[col] = 'TIMESTAMP'
                    else:
                        question_obj = questions_created[col_idx]
                        new_col_map[col] = {'question': question_obj, 'dtype': col_data['dtype'], 'unique_ops': col_data['unique_ops']}
                        col_idx += 1
                col_map = new_col_map
                
                # OPTIMIZACIÓN CRÍTICA: Bulk create de todas las opciones (N×M queries → 1 query)
                options_to_create = []
                for col, col_data in col_map.items():
                    if col_data != 'TIMESTAMP' and col_data['dtype'] in ['single', 'multi']:
                        question_obj = col_data['question']
                        for option_text in col_data['unique_ops']:
                            options_to_create.append(AnswerOption(question=question_obj, text=option_text))
                
                if options_to_create:
                    AnswerOption.objects.bulk_create(options_to_create, batch_size=5000)

                # ======================================================================
                # CORRECCIÓN APLICADA: RE-CONSULTAR PREGUNTAS PARA OBTENER OPCIONES
                # ======================================================================
                questions_with_options = {
                    q.id: q for q in survey.questions.prefetch_related('options').all()
                }

                # OPTIMIZACIÓN: Pre-cargar opciones para COPY FROM
                options_map = {}
                for col, col_data in col_map.items():
                    if col_data != 'TIMESTAMP':
                        # Usar el objeto actualizado que tiene las opciones cargadas
                        question_id = col_data['question'].id
                        fresh_question_obj = questions_with_options.get(question_id)
                        
                        options_dict = {}
                        if col_data['dtype'] in ['single', 'multi']:
                            options_dict = {op.text: op.id for op in fresh_question_obj.options.all()}
                            
                        options_map[col] = {
                            'question': fresh_question_obj,
                            'dtype': col_data['dtype'],
                            'options': options_dict
                        }

                # OPTIMIZACIÓN POSTGRESQL: Usar COPY FROM para inserción masiva ultra-rápida
                logger.info(f"Usando PostgreSQL COPY FROM para {len(df)} respuestas")
                surveys_created, answers_created = bulk_import_responses_postgres(
                    survey=survey,
                    dataframe=df,
                    questions_map=options_map,
                    date_column=date_col_name
                )
                logger.info(f"COPY FROM completado: {surveys_created} surveys, {answers_created} answers")

            # Log successful import
            logger.info(
                f"Importación CSV exitosa",
                user_id=request.user.id,
                encuesta_id=survey.id,
                rows_imported=len(df),
                columns=len(df.columns)
            )
            
            log_data_change(
                'Encuesta',
                'CREATE',
                instance_id=survey.id,
                user_id=request.user.id,
                source='csv_import',
                rows_count=len(df)
            )
            
            messages.success(
                request, 
                f"Importación exitosa: {len(df):,} registros procesados en {surveys_created:,} respuestas y {answers_created:,} respuestas individuales. "
                f"Haz clic en 'Ver Resultados' para explorar los datos."
            )
            return redirect('surveys:list')
            
        except ValidationError as e:
            logger.error(f"Error de validación en importación CSV", error=str(e), user_id=request.user.id)
            messages.error(request, str(e))
        except pd.errors.EmptyDataError:
            logger.error("Archivo CSV vacío", user_id=request.user.id)
            messages.error(request, "El archivo CSV está vacío")
        except pd.errors.ParserError as e:
            logger.error(f"Error al parsear CSV", error=str(e), user_id=request.user.id)
            messages.error(request, "El archivo CSV tiene un formato inválido")
        except Exception as e:
            logger.exception(f"Error inesperado en importación CSV: {e}")
            messages.error(request, f"Error al importar: {str(e)[:100]}")

    return redirect('surveys:list')


@login_required
@ratelimit(key='user', rate='10/h', method='POST', block=True)
def import_csv_preview_view(request):
    """Vista AJAX para generar preview del CSV antes de importar."""
    from django.http import JsonResponse
    import json
    
    if request.method == 'POST' and request.FILES.get('csv_file'):
        try:
            # Validar archivo CSV
            csv_file = CSVImportValidator.validate_csv_file(request.FILES.get('csv_file'))
            
            # Leer DataFrame con detección automática de codificación
            try:
                # Intentar varias codificaciones comunes
                encodings = [
                    'utf-8-sig',  # UTF-8 con BOM
                    'utf-8',
                    'utf-16',  # UTF-16 con BOM
                    'utf-16-le',  # UTF-16 Little Endian
                    'utf-16-be',  # UTF-16 Big Endian
                    'latin-1',
                    'iso-8859-1',
                    'cp1252',
                    'windows-1252',
                    'mac_roman'
                ]
                df = None
                last_error = None
                
                for encoding in encodings:
                    try:
                        csv_file.seek(0)  # Resetear posición del archivo
                        df = pd.read_csv(csv_file, encoding=encoding)
                        logger.info(f"CSV leído exitosamente con codificación: {encoding}")
                        break
                    except (UnicodeDecodeError, UnicodeError) as e:
                        last_error = e
                        continue
                    except Exception as e:
                        # Otros errores pueden indicar que la codificación funcionó pero hay otro problema
                        last_error = e
                        continue
                
                if df is None:
                    raise Exception(f'No se pudo leer el archivo. Asegúrate de que sea un archivo CSV válido. Intenta abrirlo en Excel y guardarlo como CSV UTF-8.')
                    
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'error': f'Error al leer el archivo CSV: {str(e)}'
                }, status=400)
            
            # Validar DataFrame
            try:
                df = CSVImportValidator.validate_dataframe(df)
            except ValidationError as e:
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                }, status=400)
            
            # Analizar estructura del CSV
            preview_data = {
                'success': True,
                'filename': csv_file.name,
                'total_rows': len(df),
                'total_columns': len(df.columns),
                'columns': [],
                'sample_rows': []
            }
            
            # Detectar tipo de cada columna
            date_col_name = None
            columns_to_analyze = []
            
            for col in df.columns:
                col_lower = col.lower()
                
                # Definir patrones de columnas a excluir
                skip_patterns = [
                    'id', 'id_respuesta', 'respuesta_id', 'response_id',
                    'fecha', 'date', 'timestamp', 'time', 'creado',
                    'usuario', 'user', 'email'
                ]
                
                col_info = {
                    'name': col,
                    'display_name': col.replace('_', ' ').title(),
                    'type': 'text',
                    'unique_values': 0,
                    'sample_values': [],
                    'is_metadata': False
                }
                
                # Detectar si es columna de fecha
                if not date_col_name and any(x in col_lower for x in ['fecha', 'date', 'timestamp', 'time', 'creado']):
                    date_col_name = col
                    col_info['type'] = 'timestamp'
                    col_info['is_timestamp'] = True
                    col_info['is_metadata'] = True
                elif any(pattern in col_lower for pattern in skip_patterns):
                    # Marcar como metadata pero incluir en preview
                    col_info['type'] = 'metadata'
                    col_info['is_metadata'] = True
                else:
                    # Analizar tipo de datos
                    sample = df[col].dropna()
                    if not sample.empty:
                        col_info['unique_values'] = sample.nunique()
                        
                        # Determinar tipo
                        if pd.api.types.is_numeric_dtype(sample):
                            if sample.min() >= 0 and sample.max() <= 10:
                                col_info['type'] = 'scale'
                            else:
                                col_info['type'] = 'number'
                        else:
                            if sample.astype(str).str.contains(',').any():
                                col_info['type'] = 'multi'
                            elif sample.nunique() < 15:
                                col_info['type'] = 'single'
                        
                        # Obtener valores de muestra (primeros 3 únicos)
                        sample_vals = sample.unique()[:3]
                        col_info['sample_values'] = [str(v) for v in sample_vals]
                
                preview_data['columns'].append(col_info)
            
            # Obtener primeras 5 filas como muestra
            sample_rows = df.head(5).values.tolist()
            preview_data['sample_rows'] = [
                [str(val) if not pd.isna(val) else '' for val in row]
                for row in sample_rows
            ]
            
            return JsonResponse(preview_data)
            
        except Exception as e:
            logger.exception(f"Error en preview CSV: {e}")
            return JsonResponse({
                'success': False,
                'error': f'Error inesperado: {str(e)[:200]}'
            }, status=500)
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)


@login_required
@ratelimit(key='user', rate='100/h', method='POST', block=True)
def import_multiple_surveys_view(request):
    """Vista para importar múltiples archivos CSV a la vez."""
    from django.http import JsonResponse
    
    if request.method == 'POST':
        files = request.FILES.getlist('csv_files')
        
        logger.info(f"=== IMPORTACIÓN MÚLTIPLE ===")
        logger.info(f"Usuario: {request.user}")
        logger.info(f"Archivos recibidos: {len(files)}")
        for f in files:
            logger.info(f"  - {f.name} ({f.size} bytes)")
        
        if not files:
            return JsonResponse({
                'success': False,
                'error': 'No se seleccionaron archivos'
            }, status=400)
        
        success_count = 0
        error_count = 0
        errors = []
        
        for csv_file in files:
            file_name = csv_file.name
            logger.info(f"Procesando archivo: {file_name}")
            try:
                # Validar archivo CSV
                csv_file = CSVImportValidator.validate_csv_file(csv_file)
                
                # Leer DataFrame con detección automática de codificación
                encodings = [
                    'utf-8-sig', 'utf-8', 'utf-16', 'utf-16-le', 'utf-16-be',
                    'latin-1', 'iso-8859-1', 'cp1252', 'windows-1252', 'mac_roman'
                ]
                df = None
                
                for encoding in encodings:
                    try:
                        csv_file.seek(0)
                        df = pd.read_csv(csv_file, encoding=encoding)
                        break
                    except (UnicodeDecodeError, UnicodeError):
                        continue
                
                if df is None:
                    errors.append(f"{csv_file.name}: No se pudo leer el archivo")
                    error_count += 1
                    continue
                
                df = CSVImportValidator.validate_dataframe(df)
                
                # Generar título desde nombre del archivo
                base_name = csv_file.name.rsplit('.', 1)[0]
                title = base_name.replace('_', ' ').replace('-', ' ').title()
                if len(title) > 255:
                    title = title[:252] + '...'
                
                with transaction.atomic():
                    survey = Survey.objects.create(
                        author=request.user,
                        title=title,
                        description=f"Importada {datetime.now().strftime('%Y-%m-%d')}",
                        status='active',
                        sample_goal=len(df)
                    )
                    
                    # Detección de columnas y creación de preguntas
                    col_map = {}
                    date_col_name = None
                    preguntas_creadas = 0
                    columnas_saltadas = 0
                    
                    logger.info(f"Procesando {len(df.columns)} columnas para {file_name}")
                    
                    for col in df.columns:
                        col = CSVImportValidator.validate_column_name(col)
                        col_lower = col.lower()
                        
                        # Patrones para saltar columnas de metadata (más específicos)
                        skip_patterns = [
                            'response_id', 'respuesta_id', 'id_respuesta',
                            'timestamp', 'creado', 'created_at', 'updated_at'
                        ]
                        
                        # Patrones para identificadores y nombres personales (solo datos contextuales puros)
                        # IMPORTANTE: Esto solo debe saltar columnas que son IDENTIDAD, no evaluaciones
                        identity_patterns = [
                            # Nombres y apellidos (con variaciones)
                            'nombre_completo', 'full_name', 'apellido', 'apellidos',
                            '^nombre$', '^name$', 'nombre_', 'name_',  # nombre + sufijo
                            # Contacto
                            'email', 'correo', 'telefono', 'phone', 
                            # Identificaciones
                            'dni', 'cedula', 'identificacion', 'documento',
                            '_id$', 'reserva_id', 'empleado_id', 'paciente_id', 'cliente_id',
                            # Demográficos
                            'nacionalidad', 'genero', 'sexo', 'gender',
                            # Tipos y clasificaciones contextuales
                            'tipo_habitacion', 'tipo_servicio', 'tipo_',
                            '^area$', '^departamento$',
                            '^carrera$', '^semestre$', '^servicio$'  # Solo exactos
                        ]
                        
                        # Detectar columna de fecha/timestamp
                        if not date_col_name and any(x in col_lower for x in ['fecha', 'date', 'timestamp', 'time', 'creado', 'periodo', 'checkout', 'check_out', 'visita']):
                            date_col_name = col
                            col_map[col] = 'TIMESTAMP'
                            logger.info(f"Columna de fecha detectada: {col}")
                            columnas_saltadas += 1
                            continue
                        
                        # Saltar IDs exactos o de respuesta
                        if col_lower == 'id' or any(pattern in col_lower for pattern in skip_patterns):
                            logger.info(f"Saltando columna de metadata: {col}")
                            columnas_saltadas += 1
                            continue
                        
                        # Saltar columnas de identificación personal (usar regex para patrones exactos)
                        import re
                        skip_column = False
                        for pattern in identity_patterns:
                            # Si el patrón tiene ^ o $, usar regex exacto
                            if '^' in pattern or '$' in pattern:
                                if re.search(pattern, col_lower):
                                    skip_column = True
                                    break
                            # Si no, buscar substring simple
                            elif pattern in col_lower:
                                skip_column = True
                                break
                        
                        if skip_column:
                            logger.info(f"Saltando columna de identificación personal: {col}")
                            columnas_saltadas += 1
                            continue
                        
                        sample = df[col].dropna()
                        if len(sample) == 0:
                            logger.warning(f"Saltando columna vacía: {col}")
                            columnas_saltadas += 1
                            continue
                        
                        # Detectar tipo de pregunta
                        unique_count = sample.nunique()
                        if pd.api.types.is_numeric_dtype(sample):
                            question_type = 'scale'
                        elif unique_count <= 20:
                            question_type = 'single'
                        else:
                            question_type = 'text'
                        
                        question = Question.objects.create(
                            survey=survey,
                            text=col,
                            type=question_type,
                            is_required=False
                        )
                        col_map[col] = question
                        preguntas_creadas += 1
                        logger.info(f"Pregunta creada: {col} (tipo: {question_type}, valores únicos: {unique_count})")
                        
                        if question_type == 'single' and unique_count <= 20:
                            for val in sample.unique():
                                if pd.notna(val):
                                    AnswerOption.objects.create(
                                        question=question,
                                        text=str(val)
                                    )
                    
                    logger.info(f"Resumen: {preguntas_creadas} preguntas creadas, {columnas_saltadas} columnas saltadas")
                    
                    # Crear respuestas usando bulk_create para optimización
                    responses_batch = []
                    question_responses_batch = []
                    batch_size = 500
                    
                    # Pre-cargar todas las opciones de respuesta para consultas rápidas
                    options_map = {}
                    for col_name, question_obj in col_map.items():
                        if question_obj != 'TIMESTAMP' and question_obj.type == 'single':
                            options = AnswerOption.objects.filter(question=question_obj)
                            options_map[question_obj.id] = {op.text: op for op in options}
                    
                    logger.info(f"Iniciando importación de {len(df)} respuestas en lotes de {batch_size}...")
                    
                    for idx, row in df.iterrows():
                        timestamp = None
                        if date_col_name and pd.notna(row.get(date_col_name)):
                            try:
                                timestamp = pd.to_datetime(row[date_col_name])
                                # Hacer timezone-aware
                                if timestamp.tzinfo is None:
                                    from django.utils import timezone as tz
                                    timestamp = tz.make_aware(timestamp)
                            except:
                                pass
                        
                        # Crear objeto de respuesta (sin guardar aún)
                        survey_response = SurveyResponse(
                            survey=survey,
                            created_at=timestamp if timestamp else timezone.now()
                        )
                        responses_batch.append(survey_response)
                        
                        # Si llegamos al tamaño del lote, guardar
                        if len(responses_batch) >= batch_size:
                            created_responses = SurveyResponse.objects.bulk_create(responses_batch)
                            
                            # Ahora crear las respuestas a preguntas
                            for i, resp in enumerate(created_responses):
                                row_data = df.iloc[idx - len(responses_batch) + i + 1]
                                for col_name, question_obj in col_map.items():
                                    if question_obj == 'TIMESTAMP':
                                        continue
                                    
                                    valor = row_data.get(col_name)
                                    if pd.isna(valor):
                                        continue
                                    
                                    if question_obj.type == 'text':
                                        question_responses_batch.append(
                                            QuestionResponse(
                                                survey_response=resp,
                                                question=question_obj,
                                                text_value=str(valor)
                                            )
                                        )
                                    elif question_obj.type == 'scale':
                                        try:
                                            question_responses_batch.append(
                                                QuestionResponse(
                                                    survey_response=resp,
                                                    question=question_obj,
                                                    numeric_value=float(valor)
                                                )
                                            )
                                        except:
                                            pass
                                    elif question_obj.type == 'single':
                                        option = options_map.get(question_obj.id, {}).get(str(valor))
                                        if option:
                                            question_responses_batch.append(
                                                QuestionResponse(
                                                    survey_response=resp,
                                                    question=question_obj,
                                                    selected_option=option
                                                )
                                            )
                            
                            # Guardar respuestas a preguntas en lote
                            if question_responses_batch:
                                QuestionResponse.objects.bulk_create(question_responses_batch, batch_size=1000)
                                question_responses_batch = []
                            
                            responses_batch = []
                            logger.info(f"Procesadas {idx + 1}/{len(df)} respuestas...")
                    
                    # Guardar respuestas restantes
                    if responses_batch:
                        created_responses = SurveyResponse.objects.bulk_create(responses_batch)
                        
                        # Crear las respuestas a preguntas para el último lote
                        for i, resp in enumerate(created_responses):
                            row_data = df.iloc[len(df) - len(responses_batch) + i]
                            for col_name, question_obj in col_map.items():
                                if question_obj == 'TIMESTAMP':
                                    continue
                                
                                valor = row_data.get(col_name)
                                if pd.isna(valor):
                                    continue
                                
                                if question_obj.type == 'text':
                                    question_responses_batch.append(
                                        QuestionResponse(
                                            survey_response=resp,
                                            question=question_obj,
                                            text_value=str(valor)
                                        )
                                    )
                                elif question_obj.type == 'scale':
                                    try:
                                        question_responses_batch.append(
                                            QuestionResponse(
                                                survey_response=resp,
                                                question=question_obj,
                                                numeric_value=float(valor)
                                            )
                                        )
                                    except:
                                        pass
                                elif question_obj.type == 'single':
                                    option = options_map.get(question_obj.id, {}).get(str(valor))
                                    if option:
                                        question_responses_batch.append(
                                            QuestionResponse(
                                                survey_response=resp,
                                                question=question_obj,
                                                selected_option=option
                                            )
                                        )
                        
                        if question_responses_batch:
                            QuestionResponse.objects.bulk_create(question_responses_batch, batch_size=1000)
                
                success_count += 1
                logger.info(f"✓ Importación exitosa: {file_name} ({len(df)} respuestas)")
                
            except Exception as e:
                error_count += 1
                error_msg = str(e)[:200]
                errors.append(f"{file_name}: {error_msg}")
                logger.error(f"✗ Error importando {file_name}: {e}", exc_info=True)
        
        if success_count > 0:
            message = f'Se importaron {success_count} encuesta(s) exitosamente.'
            if error_count > 0:
                message += f' {error_count} archivo(s) fallaron.'
            
            return JsonResponse({
                'success': True,
                'imported': success_count,
                'errors': error_count,
                'error_details': errors,
                'message': message
            })
        else:
            error_message = 'No se pudo importar ningún archivo.'
            if errors:
                error_message += ' Errores: ' + '; '.join(errors[:3])
            
            return JsonResponse({
                'success': False,
                'error': error_message,
                'all_errors': errors
            }, status=400)
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)


@login_required
def import_responses_view(request, pk):
    return redirect('surveys:detail', pk=pk)


@login_required
@ratelimit(key='user', rate='10/h', method='GET', block=True)
def export_survey_csv_view(request, pk):
    """Exportar resultados de encuesta a CSV."""
    from django.http import HttpResponse
    import csv
    from datetime import datetime
    
    survey = get_object_or_404(Survey, pk=pk, author=request.user)
    
    # Obtener todas las respuestas con prefetch optimizado
    respuestas = SurveyResponse.objects.filter(survey=survey).prefetch_related(
        'question_responses__question',
        'question_responses__selected_option'
    ).order_by('created_at')
    
    if not respuestas.exists():
        messages.warning(request, "No hay respuestas para exportar en esta encuesta.")
        return redirect('surveys:resultados', pk=pk)
    
    # Crear respuesta HTTP con CSV
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    filename = f"{survey.title.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Agregar BOM para Excel en español
    response.write('\ufeff')
    
    writer = csv.writer(response)
    
    # Obtener todas las preguntas en orden
    preguntas = list(
        survey.questions.prefetch_related('options')
        .all()
        .order_by('order')
    )
    
    # Escribir encabezados
    headers = ['ID_Respuesta', 'Fecha', 'Usuario']
    headers.extend([p.text for p in preguntas])
    writer.writerow(headers)
    
    # Escribir datos
    for respuesta in respuestas:
        row = [
            respuesta.id,
            respuesta.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            respuesta.user.username if respuesta.user else 'Anónimo'
        ]
        
        # Crear mapa de respuestas por pregunta
        respuestas_map = {}
        for rp in respuesta.question_responses.all():
            pregunta_id = rp.question.id
            
            # Determinar el valor según el tipo
            if rp.numeric_value is not None:
                valor = str(rp.numeric_value)
            elif rp.selected_option:
                valor = rp.selected_option.text
            elif rp.text_value:
                valor = rp.text_value
            else:
                valor = ''
            
            # Si ya existe una respuesta para esta pregunta (multi), concatenar
            if pregunta_id in respuestas_map:
                respuestas_map[pregunta_id] += f", {valor}"
            else:
                respuestas_map[pregunta_id] = valor
        
        # Agregar respuestas en el orden de las preguntas
        for pregunta in preguntas:
            row.append(respuestas_map.get(pregunta.id, ''))
        
        writer.writerow(row)
    
    # Log de exportación
    logger.info(
        f"Exportación CSV exitosa",
        user_id=request.user.id,
        survey_id=survey.id,
        total_respuestas=respuestas.count()
    )
    
    return response


@ratelimit(key='ip', rate='60/h', method='POST', block=True)
def respond_survey_view(request, pk):
    """Vista para responder una encuesta pública."""
    survey = get_object_or_404(
        Survey.objects.prefetch_related('questions__options'),
        pk=pk
    )
    
    # Validar que la encuesta esté activa usando helper
    if not PermissionHelper.verify_encuesta_is_active(survey):
        messages.warning(request, "Esta encuesta no está activa actualmente")
        return redirect('surveys:thanks')
    
    if request.method == 'POST':
        try:
            with transaction.atomic():
                user_obj = request.user if request.user.is_authenticated else None
                survey_response = SurveyResponse.objects.create(
                    survey=survey,
                    user=user_obj,
                    is_anonymous=(user_obj is None)
                )
                
                # OPTIMIZACIÓN: Cachear preguntas para evitar doble query
                questions_cached = list(survey.questions.prefetch_related('options').all())
                
                # Recopilar IDs de opciones para bulk fetch
                all_option_ids = []
                for q in questions_cached:
                    field = f'pregunta_{q.id}'
                    if q.type == 'multi':
                        opts = request.POST.getlist(field)
                        all_option_ids.extend(opts)
                    elif q.type == 'single':
                        val = request.POST.get(field)
                        if val:
                            all_option_ids.append(val)
                
                # Bulk fetch all options to avoid N+1
                options_map = {str(op.id): op for op in AnswerOption.objects.filter(id__in=all_option_ids)}
                
                for q in questions_cached:
                    field = f'pregunta_{q.id}'
                    if q.type == 'multi':
                        opts = request.POST.getlist(field)
                        txts = [options_map[o].text for o in opts if o in options_map]
                        if txts:
                            QuestionResponse.objects.create(
                                survey_response=survey_response,
                                question=q,
                                text_value=",".join(txts)
                            )
                    else:
                        val = request.POST.get(field)
                        if val:
                            if q.type in ['number', 'scale']:
                                try:
                                    # Validar respuesta numérica
                                    if q.type == 'scale':
                                        validated_value = ResponseValidator.validate_scale_response(val)
                                    else:
                                        validated_value = ResponseValidator.validate_numeric_response(val)
                                    QuestionResponse.objects.create(
                                        survey_response=survey_response, 
                                        question=q,
                                        numeric_value=int(validated_value)
                                    )
                                except ValidationError as e:
                                    logger.warning(f"Respuesta numérica inválida para pregunta {q.id}: {e}")
                                    # Continuar con otras preguntas
                            elif q.type == 'single':
                                option_obj = options_map.get(val)
                                if option_obj: 
                                    QuestionResponse.objects.create(
                                        survey_response=survey_response,
                                        question=q,
                                        selected_option=option_obj
                                    )
                            else:
                                validated_text = ResponseValidator.validate_text_response(val)
                                if validated_text:
                                    QuestionResponse.objects.create(
                                        survey_response=survey_response,
                                        question=q,
                                        text_value=validated_text
                                    )

                logger.info(f"Respuesta registrada exitosamente para encuesta {survey.id}")
                return redirect('surveys:thanks')
                
        except ValidationError as e:
            logger.error(f"Error de validación al responder encuesta {pk}: {e}")
            messages.error(request, str(e))
        except Exception as e:
            logger.exception(f"Error inesperado al guardar respuesta de encuesta {pk}: {e}")
            messages.error(request, "Ocurrió un error al guardar su respuesta. Por favor intente nuevamente.")
            
    return render(request, 'surveys/fill.html', {'survey': survey})


def survey_thanks_view(request):
    return render(request, 'surveys/thanks.html')


@login_required
def survey_results_view(request, pk):
    """
    Vista INDIVIDUAL de resultados de una encuesta específica.
    Incluye gráficos, estadísticas, filtros por fecha y segmentación.
    
    URL: /surveys/<pk>/resultados/
    Diferencia con dashboard_results_view (core/views.py):
    - Esta vista: Análisis detallado de UNA encuesta específica con filtros
    - dashboard_results_view: Panorama general de todas las encuestas
    
    Args:
        request: HttpRequest
        pk: ID de la encuesta a analizar
    """
    from core.services.survey_analysis import SurveyAnalysisService
    from core.validators import DateFilterValidator
    from core.utils.helpers import DateFilterHelper
    from django.db.models import Avg
    
    # Cargar encuesta con optimizaciones
    survey = get_object_or_404(
        Survey.objects.prefetch_related('questions__options'),
        pk=pk
    )
    
    # Verificar permisos
    PermissionHelper.verify_encuesta_access(survey, request.user)
    
    # Obtener respuestas base
    respuestas_qs = SurveyResponse.objects.filter(survey=survey).select_related('survey')
    
    # Procesar filtros de fecha
    start = request.GET.get('start')
    end = request.GET.get('end')
    
    if start or end:
        respuestas_qs, _ = DateFilterHelper.apply_filters(respuestas_qs, start, end)
    
    # Procesar filtro de segmentación
    segment_col = request.GET.get('segment_col', '').strip()
    segment_val = request.GET.get('segment_val', '').strip()
    
    if segment_col and segment_val:
        # Filtrar por pregunta específica que contenga el valor
        pregunta_filtro = survey.questions.filter(text__icontains=segment_col).first()
        if pregunta_filtro:
            # Construir filtro según el tipo de pregunta
            from django.db.models import Q
            
            q_filter = Q()
            if pregunta_filtro.type == 'text':
                # Preguntas de texto: buscar en text_value
                q_filter = Q(text_value__icontains=segment_val)
            elif pregunta_filtro.type == 'single':
                # Preguntas de opción única: buscar en selected_option__text
                q_filter = Q(selected_option__text__icontains=segment_val)
            elif pregunta_filtro.type == 'scale':
                # Preguntas numéricas: convertir a número y comparar
                try:
                    valor_num = float(segment_val)
                    q_filter = Q(numeric_value=valor_num)
                except ValueError:
                    # Si no es número válido, no filtrar
                    q_filter = Q(pk__isnull=True)
            elif pregunta_filtro.type == 'multi':
                # Preguntas de opción múltiple: buscar en selected_option__text
                q_filter = Q(selected_option__text__icontains=segment_val)
            else:
                # Otros tipos: buscar en cualquier campo
                q_filter = Q(text_value__icontains=segment_val) | Q(selected_option__text__icontains=segment_val)
            
            respuestas_ids = QuestionResponse.objects.filter(
                question=pregunta_filtro
            ).filter(q_filter).values_list('survey_response_id', flat=True)
            
            respuestas_qs = respuestas_qs.filter(id__in=respuestas_ids)
    
    total_respuestas = respuestas_qs.count()
    
    # Generar datos de análisis usando el servicio
    cache_key = f"survey_results_{pk}_{start or 'all'}_{end or 'all'}_{segment_col}_{segment_val}"
    
    analysis_result = SurveyAnalysisService.get_analysis_data(
        survey, 
        respuestas_qs, 
        include_charts=True,
        cache_key=cache_key
    )
    
    # Calcular métricas adicionales
    promedio_satisfaccion = 0
    preguntas_escala = survey.questions.filter(type='scale')
    if preguntas_escala.exists():
        vals = QuestionResponse.objects.filter(
            question__in=preguntas_escala,
            survey_response__in=respuestas_qs,
            numeric_value__isnull=False
        ).aggregate(avg=Avg('numeric_value'))
        promedio_satisfaccion = vals['avg'] or 0
    
    # Top 3 insights para destacar
    top_insights = [item for item in analysis_result['analysis_data'] if item.get('insight')][:3]
    
    # Generar datos para el gráfico de tendencia histórica
    from django.db.models import Count
    from django.db.models.functions import TruncDate
    import json
    
    trend_data = None
    if total_respuestas > 0:
        daily_counts = respuestas_qs.annotate(
            dia=TruncDate('created_at')
        ).values('dia').annotate(
            count=Count('id')
        ).order_by('dia')
        
        if daily_counts:
            trend_data = {
                'labels': [item['dia'].strftime('%Y-%m-%d') for item in daily_counts],
                'data': [item['count'] for item in daily_counts]
            }
    
    # Serializar analysis_data para JavaScript
    analysis_data_json = []
    for item in analysis_result['analysis_data']:
        # Extraer datos del gráfico según el formato generado por el servicio
        chart_labels = []
        chart_data = []
        
        if item.get('chart_data'):
            # El servicio devuelve {'labels': [...], 'data': [...]}
            chart_labels = item['chart_data'].get('labels', [])
            chart_data = item['chart_data'].get('data', [])
        
        analysis_data_json.append({
            'id': item.get('id'),
            'text': item.get('text'),
            'type': item.get('type'),
            'order': item.get('order'),
            'chart_labels': chart_labels,
            'chart_data': chart_data,
            'insight': item.get('insight', '')
        })
    
    context = {
        'survey': survey,
        'total_respuestas': total_respuestas,
        'nps_score': analysis_result['nps_data'].get('score', 0),
        'nps_data': analysis_result['nps_data'],  # Pasar todo el objeto NPS con insight
        'metrics': {
            'promedio_satisfaccion': round(promedio_satisfaccion, 1) if promedio_satisfaccion else None
        },
        'analysis_data': analysis_result['analysis_data'],
        'analysis_data_json': json.dumps(analysis_data_json),
        'trend_data': json.dumps(trend_data) if trend_data else None,
        'top_insights': top_insights,
        'heatmap_image': analysis_result.get('heatmap_image'),
        'preguntas_filtro': survey.questions.filter(type__in=['single', 'text', 'scale']).order_by('order'),
        'filter_start': start,
        'filter_end': end,
        'filter_col': segment_col,
        'filter_val': segment_val,
    }
    
    return render(request, 'surveys/results.html', context)


@login_required
def cambiar_estado_encuesta(request, pk):
    """
    Cambiar el estado de una encuesta (draft, active, closed).
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    survey = get_object_or_404(Survey, pk=pk, author=request.user)
    
    try:
        data = json.loads(request.body)
        nuevo_estado = data.get('status', data.get('estado'))
        
        # Validar estado
        estados_validos = ['draft', 'active', 'closed']
        if nuevo_estado not in estados_validos:
            return JsonResponse({'error': 'Estado no válido'}, status=400)
        
        # Actualizar estado
        estado_anterior = survey.status
        survey.status = nuevo_estado
        survey.save(update_fields=['status'])
        
        # Log del cambio
        log_data_change(
            'UPDATE',
            'Encuesta',
            survey.id,
            request.user.id,
            changes={'estado': f'{estado_anterior} → {nuevo_estado}'}
        )
        
        return JsonResponse({
            'success': True,
            'nuevo_estado': nuevo_estado,
            'mensaje': f'Estado actualizado a {dict(Survey.STATUS_CHOICES).get(nuevo_estado, nuevo_estado)}'
        })
        
    except Exception as e:
        logger.exception(f"Error al cambiar estado de encuesta {pk}: {e}")
        return JsonResponse({'error': str(e)}, status=500)