import threading
import time
import psutil
import logging
import os
import tempfile
import importlib

cpp_csv = importlib.import_module('cpp_csv')

from celery.result import AsyncResult
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from django.apps import apps
from django.db import transaction
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(levelname)s] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

# Intentar importar el modelo Survey
try:
    from surveys.models import Survey
except ImportError:
    Survey = apps.get_model('surveys', 'Survey')

# =============================================================================
# Utilidad para monitorear el uso máximo de RAM
# =============================================================================
class MaxRAMMonitor:
    def __init__(self, interval=0.2):
        self.interval = interval
        self.max_rss = 0
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._monitor)

    def _monitor(self):
        process = psutil.Process()
        while not self._stop_event.is_set():
            rss = process.memory_info().rss
            if rss > self.max_rss:
                self.max_rss = rss
            time.sleep(self.interval)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._thread.join()

    def get_max_rss_mb(self):
        return self.max_rss / (1024 * 1024)

# =============================================================================
# Helpers Síncronos (I/O)
# =============================================================================
def _get_import_base_dir() -> str:
    base_dir = getattr(settings, "SURVEY_IMPORT_BASE_DIR", None)
    if not base_dir:
        media_root = getattr(settings, "MEDIA_ROOT", None)
        if media_root:
            base_dir = os.path.join(media_root, "imports")
        else:
            base_dir = os.path.join(settings.BASE_DIR, "tmp", "imports")
    os.makedirs(base_dir, exist_ok=True)
    return base_dir

def _save_uploaded_csv(upload) -> str:
    """
    Guarda el archivo subido en disco. Debe ejecutarse en un contexto síncrono.
    """
    base_dir = _get_import_base_dir()
    _, ext = os.path.splitext(upload.name)
    if not ext: ext = ".csv"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, dir=base_dir)
    try:
        for chunk in upload.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name
    finally:
        tmp.close()
    return tmp_path

# =============================================================================
# Test helper expected by surveys/tests/test_import_full.py
# =============================================================================
def _process_single_csv_import(uploaded_file, user):
    """
    Minimal, deterministic CSV import helper used by tests.

    Crea una encuesta, preguntas y respuestas a partir de un CSV sencillo con
    columnas que representan tipos (single, multi, number, scale, text).
    Devuelve (survey, total_rows, info_dict).
    """
    import csv
    from io import StringIO
    from django.utils.text import slugify
    from surveys.models import Survey, Question, AnswerOption, SurveyResponse, QuestionResponse

    # Leer contenido en memoria
    content = uploaded_file.read()
    if isinstance(content, bytes):
        text = content.decode('utf-8')
    else:
        text = str(content)
    f = StringIO(text)
    reader = csv.DictReader(f)
    rows = list(reader)

    # Crear encuesta
    title = getattr(uploaded_file, 'name', 'Imported Survey')
    if user is None:
        raise ValueError("El usuario (author) no puede ser None al importar una encuesta desde CSV.")
    survey = Survey.objects.create(
        title=f"{os.path.splitext(title)[0]}",
        description="Importación de prueba",
        author=user,
        status='active'
    )

    # Inferir tipos por nombre de columna
    def infer_type(col_name: str) -> str:
        c = col_name.lower()
        if 'multi' in c:
            return 'multi'
        if 'single' in c:
            return 'single'
        if 'number' in c:
            return 'number'
        if 'scale' in c:
            return 'scale'
        return 'text'

    headers = reader.fieldnames or []
    questions = []
    for idx, col in enumerate(headers):
        qtype = infer_type(col)
        q = Question.objects.create(
            survey=survey,
            text=col,
            type=qtype,
            order=idx + 1,
        )
        questions.append(q)

    # Crear opciones para single/multi basadas en valores únicos
    from collections import defaultdict
    unique_values = defaultdict(set)
    for row in rows:
        for q in questions:
            val = (row.get(q.text) or '').strip()
            if q.type in ('single', 'multi') and val:
                if q.type == 'multi':
                    parts = [p.strip() for p in val.split(',') if p.strip()]
                    for p in parts:
                        unique_values[q.id].add(p)
                else:
                    unique_values[q.id].add(val)

    options_map = {}
    for q in questions:
        if q.id in unique_values:
            for order, opt_text in enumerate(sorted(unique_values[q.id])):
                opt = AnswerOption.objects.create(question=q, text=opt_text, order=order)
                options_map.setdefault(q.id, {})[opt_text] = opt

    # Crear respuestas
    for row in rows:
        sr = SurveyResponse.objects.create(survey=survey, user=user)
        for q in questions:
            raw = (row.get(q.text) or '').strip()
            if not raw:
                continue
            if q.type == 'single':
                opt = options_map.get(q.id, {}).get(raw)
                QuestionResponse.objects.create(survey_response=sr, question=q, selected_option=opt)
            elif q.type == 'multi':
                for token in [p.strip() for p in raw.split(',') if p.strip()]:
                    opt = options_map.get(q.id, {}).get(token)
                    QuestionResponse.objects.create(survey_response=sr, question=q, selected_option=opt)
            elif q.type in ('number', 'scale'):
                try:
                    num = int(float(raw))
                except ValueError:
                    num = None
                QuestionResponse.objects.create(survey_response=sr, question=q, numeric_value=num)
            else:
                QuestionResponse.objects.create(survey_response=sr, question=q, text_value=raw)

    info = {'created_questions': len(questions)}
    return survey, len(rows), info

# =============================================================================
# Servicios Síncronos (Lógica de Negocio + DB + Celery)
# =============================================================================

def service_create_import_job(user, uploaded_file, survey_title=None, is_bulk=False):
    """
    Maneja la creación de la encuesta, guardado de archivo y lanzamiento de Celery
    de forma atómica y síncrona.
    """
    from surveys.tasks import process_survey_import
    from surveys.utils.bulk_import import _infer_column_type
    import tempfile
    import json

    # 1. Guardar archivo temporalmente
    file_path = _save_uploaded_csv(uploaded_file)

    # 2. Leer primeras filas para inferir esquema
    rows = cpp_csv.read_csv_dicts(file_path)
    if not rows:
        return {'success': False, 'error': 'El archivo CSV está vacío o no tiene datos válidos.'}
    first_row = rows[0]
    schema = {}
    for col in first_row.keys():
        # Tomar muestra de hasta 50 valores no vacíos
        sample = [str(r.get(col, '')) for r in rows[:50] if r.get(col, '')]
        dtype = _infer_column_type(col, sample)
        schema[col] = {'type': dtype}

    # 3. Validar todo el archivo con cpp_csv
    validation_result = cpp_csv.read_and_validate_csv(file_path, schema)
    if validation_result.get('errors'):
        return {
            'success': False,
            'error': 'Errores de validación en el archivo CSV.',
            'validation_errors': validation_result['errors']
        }

    # 4. Crear registro en DB solo si pasa validación
    with transaction.atomic():
        title_to_use = survey_title or uploaded_file.name
        new_survey = Survey.objects.create(
            author=user,
            title=title_to_use,
            description="Importación masiva desde CSV" if is_bulk else "Importada desde CSV",
            status='closed' if is_bulk else 'active',
            is_imported=True
        )

    # 5. Lanzar Celery (Network I/O)
    task = process_survey_import.delay(
        survey_id=new_survey.id,
        file_path=file_path,
        filename=uploaded_file.name,
        user_id=user.id
    )

    return {
        'success': True,
        'job_id': task.id,
        'filename': uploaded_file.name,
        'survey_public_id': new_survey.public_id,
        'survey_id': new_survey.id
    }

def service_import_to_existing_survey(user, public_id, uploaded_file):
    """
    Importa CSV a una encuesta existente.
    """
    from surveys.tasks import process_survey_import
    
    survey = Survey.objects.filter(public_id=public_id, author=user).first()
    if not survey:
        return None

    file_path = _save_uploaded_csv(uploaded_file)
    
    task = process_survey_import.delay(
        survey_id=survey.id,
        file_path=file_path,
        filename=uploaded_file.name,
        user_id=user.id
    )
    
    return {
        'task_id': task.id,
        'survey_public_id': survey.public_id
    }

def service_generate_preview(uploaded_file):
    """
    Genera el preview usando cpp_csv de forma síncrona.
    """
    try:
        # Guardar archivo temporal para pasarlo a C++
        import tempfile
        with tempfile.NamedTemporaryFile(delete=True, suffix='.csv') as tmp:
            uploaded_file.seek(0)
            for chunk in uploaded_file.chunks():
                tmp.write(chunk)
            tmp.flush()
            # Leer con cpp_csv
            rows = cpp_csv.read_csv_dicts(tmp.name)
            if not rows:
                return {"success": False, "error": "El archivo está vacío o no tiene datos válidos."}
            columns_info = []
            from surveys.utils.bulk_import import _infer_column_type
            # Tomar las claves del primer dict como columnas
            first_row = rows[0]
            for col in first_row.keys():
                sample = [str(r.get(col, '')) for r in rows if r.get(col, '')]
                dtype = _infer_column_type(col, sample)
                sample_values = list({str(r.get(col, '')) for r in rows if r.get(col, '')})[:10]
                columns_info.append({
                    "name": col,
                    "dtype": dtype,
                    "type": dtype,
                    "display_name": col,
                    "unique_values": len(set(sample)),
                    "sample_values": sample_values
                })
            sample_rows = [[r.get(col, '') for col in first_row.keys()] for r in rows[:5]]
            return {
                "success": True,
                "columns": columns_info,
                "sample_rows": sample_rows,
                "filename": uploaded_file.name,
                "total_rows": len(rows)
            }
    except Exception as exc:
        return {"success": False, "error": str(exc)}

# =============================================================================
# Vistas Async (Corregidas para acceso seguro al Usuario y DB)
# =============================================================================

@csrf_exempt
async def csv_create_start_import(request: HttpRequest) -> JsonResponse:
    """
    Crea encuestas e inicia importación.
    Usa await request.auser() para evitar SynchronousOnlyOperation.
    """
    # CORRECCIÓN CLAVE: Usar auser() para cargar el usuario asíncronamente
    user = await request.auser()
    logger.debug(f"[IMPORT][DEBUG] Method: {request.method}, FILES: {list(request.FILES.keys())}, POST: {list(request.POST.keys())}")
    if not user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'No autorizado.'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido.'}, status=405)

    ram_monitor = MaxRAMMonitor()
    ram_monitor.start()

    try:
        # 1. Caso Bulk Import
        if 'csv_files' in request.FILES:
            files = request.FILES.getlist('csv_files')
            jobs = []
            for uploaded_file in files:
                result = await sync_to_async(service_create_import_job)(
                    user=user,  # Pasamos el usuario ya cargado
                    uploaded_file=uploaded_file, 
                    is_bulk=True
                )
                if not result.get('success', True):
                    ram_monitor.stop()
                    return JsonResponse({
                        'success': False,
                        'error': result.get('error', 'Errores de validación en el archivo CSV.'),
                        'validation_errors': result.get('validation_errors', [])
                    }, status=400)
                jobs.append(result)

            ram_monitor.stop()
            logger.info(f"[IMPORT][RAM] Bulk import: {ram_monitor.get_max_rss_mb():.2f} MB")
            return JsonResponse({
                'success': True,
                'message': f'{len(jobs)} importaciones iniciadas.',
                'jobs': jobs
            })

        # 2. Caso Single Import
        elif 'csv_file' in request.FILES:
            uploaded_file = request.FILES['csv_file']
            survey_title = request.POST.get('survey_title', '').strip()

            result = await sync_to_async(service_create_import_job)(
                user=user, # Pasamos el usuario ya cargado
                uploaded_file=uploaded_file,
                survey_title=survey_title,
                is_bulk=False
            )
            if not result.get('success', True):
                ram_monitor.stop()
                return JsonResponse({
                    'success': False,
                    'error': result.get('error', 'Errores de validación en el archivo CSV.'),
                    'validation_errors': result.get('validation_errors', [])
                }, status=400)

            ram_monitor.stop()
            logger.info(f"[IMPORT][RAM] Single import: {ram_monitor.get_max_rss_mb():.2f} MB")
            return JsonResponse({
                'success': True,
                'message': 'Importación iniciada.',
                'job_id': result['job_id'],
                'survey_public_id': result['survey_public_id']
            })

        else:
            ram_monitor.stop()
            return JsonResponse({'success': False, 'error': 'No se recibió archivo CSV.'}, status=400)

    except Exception as exc:
        ram_monitor.stop()
        logger.error(f"[IMPORT_VIEW][ERROR] {exc}", exc_info=True)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@csrf_exempt
async def csv_create_preview_view(request: HttpRequest) -> JsonResponse:
    # CORRECCIÓN CLAVE: Usar auser()
    user = await request.auser()
    if not user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'No autorizado.'}, status=401)
        
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido.'}, status=405)

    return await csv_preview_view(request, public_id=None)


@csrf_exempt
async def csv_upload_start_import(request: HttpRequest, public_id: str) -> JsonResponse:
    # CORRECCIÓN CLAVE: Usar auser()
    user = await request.auser()
    if not user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'No autorizado.'}, status=401)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido.'}, status=405)

    if 'survey_file' not in request.FILES:
        return JsonResponse({'success': False, 'error': 'Falta archivo.'}, status=400)

    uploaded_file = request.FILES['survey_file']

    try:
        result = await sync_to_async(service_import_to_existing_survey)(
            user=user, # Pasamos el usuario ya cargado
            public_id=public_id,
            uploaded_file=uploaded_file
        )
        
        if not result:
            return JsonResponse({'success': False, 'error': 'Encuesta no encontrada o error al procesar.'}, status=404)

        return JsonResponse({'success': True, **result})
        
    except Exception as exc:
        logger.error(f"[IMPORT_EXISTING][ERROR] {exc}", exc_info=True)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@csrf_exempt
async def get_task_status_view(request: HttpRequest, task_id: str) -> JsonResponse:
    # Verificación manual de autenticación y método usando auser() para evitar acceso a session en async
    user = await request.auser()
    if not user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'No autorizado.'}, status=401)
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'Método no permitido.'}, status=405)
    """
    Consulta estado de Celery.
    """
    def _get_status_sync(tid):
        result = AsyncResult(tid)
        response = {'task_id': tid, 'status': result.status.lower()}

        if result.state == 'SUCCESS':
            response['status'] = 'completed'
            response['result'] = result.result
        elif result.state == 'FAILURE':
            # Si el resultado es un dict con errores de validación, propagarlo
            if isinstance(result.result, dict) and result.result.get('status') == 'FAILURE':
                response['status'] = 'failed'
                response['error_message'] = result.result.get('error', str(result.result))
                response['validation_errors'] = result.result.get('validation_errors', [])
            else:
                response['status'] = 'failed'
                response['error_message'] = str(result.result)
        else:
            response['status'] = 'processing'
            if isinstance(result.info, dict):
                response['progress'] = result.info.get('progress', 0)
        return response

    try:
        response_data = await sync_to_async(_get_status_sync, thread_sensitive=True)(task_id)
        return JsonResponse(response_data)
    except Exception as e:
        return JsonResponse({"status": "failed", "error": str(e)}, status=500)


@csrf_exempt
async def csv_preview_view(request: HttpRequest, public_id: str = None) -> JsonResponse:
    # CORRECCIÓN CLAVE: Usar auser()
    user = await request.auser()
    if not user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'No autorizado.'}, status=401)

    uploaded_file = request.FILES.get('survey_file') or request.FILES.get('csv_file')
    
    if not uploaded_file:
        return JsonResponse({'success': False, 'error': 'No file uploaded'}, status=400)

    response_data = await sync_to_async(service_generate_preview)(uploaded_file)
    
    status_code = 200 if response_data.get('success') else 400
    return JsonResponse(response_data, status=status_code)


@login_required
async def import_responses_view(request: HttpRequest, public_id: str) -> HttpResponse:
    return await sync_to_async(redirect)(reverse('surveys:detail', args=[public_id]))