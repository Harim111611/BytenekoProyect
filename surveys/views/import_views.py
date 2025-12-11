import threading
import time
import psutil
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
import logging
import os
import tempfile
import pandas as pd
from typing import Dict, Any

from celery.result import AsyncResult
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.apps import apps

logger = logging.getLogger(__name__)

# Intentar importar el modelo Survey
try:
    from surveys.models import Survey
except ImportError:
    Survey = apps.get_model('surveys', 'Survey')

# =============================================================================
# Helpers
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
# Vistas de CREACIÓN DE ENCUESTA DESDE CSV (Listado)
# =============================================================================

@require_POST
@csrf_exempt
@login_required
def csv_create_start_import(request: HttpRequest) -> JsonResponse:
    """
    Crea una o varias encuestas nuevas y lanza la importación.
    Maneja tanto carga individual ('csv_file') como múltiple ('csv_files').
    """
    from surveys.tasks import process_survey_import  # Import local para evitar ciclos
    ram_monitor = MaxRAMMonitor()
    ram_monitor.start()

    # 1. Caso de Múltiples Archivos (Bulk Import)
    if 'csv_files' in request.FILES:
        files = request.FILES.getlist('csv_files')
        jobs = []

        try:
            for uploaded_file in files:
                # Usar el nombre del archivo como título por defecto
                survey_title = uploaded_file.name
                
                # Crear encuesta
                new_survey = Survey.objects.create(
                    author=request.user,
                    title=survey_title,
                    description="Importación masiva desde CSV",
                    status='active',
                    is_imported=True
                )

                # Guardar archivo y lanzar tarea
                file_path = _save_uploaded_csv(uploaded_file)
                task = process_survey_import.delay(
                    survey_id=new_survey.id,
                    file_path=file_path,
                    filename=uploaded_file.name,
                    user_id=request.user.id
                )
                
                jobs.append({
                    'job_id': task.id,
                    'filename': uploaded_file.name,
                    'survey_public_id': new_survey.public_id
                })
            
            ram_monitor.stop()
            logger.info(f"[IMPORT][RAM] Máximo uso de RAM durante importación: {ram_monitor.get_max_rss_mb():.2f} MB")
            return JsonResponse({
                'success': True,
                'message': f'{len(jobs)} importaciones iniciadas.',
                'jobs': jobs  # El frontend espera esta lista para el polling múltiple
            })

        except Exception as exc:
            logger.error(f"[IMPORT_BULK][ERROR] {exc}", exc_info=True)
            return JsonResponse({"success": False, "error": str(exc)}, status=500)

    # 2. Caso de Archivo Único (Legacy / Flujo normal)
    elif 'csv_file' in request.FILES:
        uploaded_file = request.FILES['csv_file']
        survey_title = request.POST.get('survey_title', '').strip() or uploaded_file.name

        try:
            # Crear la encuesta nueva
            new_survey = Survey.objects.create(
                author=request.user,
                title=survey_title,
                description="Importada desde CSV",
                status='active',
                is_imported=True
            )

            # Guardar archivo
            file_path = _save_uploaded_csv(uploaded_file)

            # Lanzar Tarea
            task = process_survey_import.delay(
                survey_id=new_survey.id,
                file_path=file_path,
                filename=uploaded_file.name,
                user_id=request.user.id
            )

            ram_monitor.stop()
            logger.info(f"[IMPORT][RAM] Máximo uso de RAM durante importación: {ram_monitor.get_max_rss_mb():.2f} MB")
            return JsonResponse({
                'success': True,
                'message': 'Importación iniciada.',
                'job_id': task.id, 
                'survey_public_id': new_survey.public_id
            })

        except Exception as exc:
            ram_monitor.stop()
            logger.error(f"[IMPORT_NEW][ERROR] {exc}", exc_info=True)
            return JsonResponse({"success": False, "error": str(exc)}, status=500)

    # 3. Error si no hay archivos
    else:
        ram_monitor.stop()
        return JsonResponse({'success': False, 'error': 'No se recibió archivo CSV (csv_file o csv_files).'}, status=400)


@require_POST
@csrf_exempt
@login_required
def csv_create_preview_view(request: HttpRequest) -> JsonResponse:
    """
    Preview genérico para el modal del listado (no requiere survey existente).
    """
    if 'csv_file' not in request.FILES:
        return JsonResponse({'success': False, 'error': 'Falta archivo.'}, status=400)
    
    # Reutilizamos la lógica de preview
    return csv_preview_view(request, public_id=None) 


# =============================================================================
# Vistas de IMPORTACIÓN EN ENCUESTA EXISTENTE (Detalle)
# =============================================================================

@require_POST
@csrf_exempt
@login_required
def csv_upload_start_import(request: HttpRequest, public_id: str) -> JsonResponse:
    """
    Importa datos a una encuesta existente.
    """
    from surveys.tasks import process_survey_import 

    if 'survey_file' not in request.FILES:
        return JsonResponse({'success': False, 'error': 'Falta archivo.'}, status=400)

    survey = Survey.objects.filter(public_id=public_id, author=request.user).first()
    if not survey:
        return JsonResponse({'success': False, 'error': 'Encuesta no encontrada.'}, status=404)

    uploaded_file = request.FILES['survey_file']
    
    try:
        file_path = _save_uploaded_csv(uploaded_file)
        task = process_survey_import.delay(
            survey_id=survey.id,
            file_path=file_path, 
            filename=uploaded_file.name,
            user_id=request.user.id
        )
        return JsonResponse({
            'success': True, 
            'task_id': task.id, 
            'survey_public_id': survey.public_id 
        })
    except Exception as exc:
        logger.error(f"[IMPORT_EXISTING][ERROR] {exc}", exc_info=True)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)


@require_GET
@login_required
def get_task_status_view(request: HttpRequest, task_id: str) -> JsonResponse:
    """
    Consulta estado de Celery.
    """
    try:
        result = AsyncResult(task_id)
        response = {'task_id': task_id, 'status': result.status.lower()}
        
        if result.state == 'SUCCESS':
            response['status'] = 'completed' # Mapeo para compatibilidad con JS antiguo
            response['result'] = result.result
        elif result.state == 'FAILURE':
            response['status'] = 'failed'
            response['error_message'] = str(result.result)
        else:
            response['status'] = 'processing' # Mapeo para JS antiguo
            
        return JsonResponse(response)
    except Exception as e:
        return JsonResponse({"status": "failed", "error": str(e)}, status=500)


@require_POST
@csrf_exempt
@login_required
def csv_preview_view(request: HttpRequest, public_id: str = None) -> JsonResponse:
    """
    Lógica de preview compartida.
    """
    # Detectar el archivo ya sea 'survey_file' (detalle) o 'csv_file' (listado)
    uploaded_file = request.FILES.get('survey_file') or request.FILES.get('csv_file')
    
    if not uploaded_file:
        return JsonResponse({'success': False, 'error': 'No file uploaded'}, status=400)

    try:
        try:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, nrows=5, encoding='utf-8-sig')
        except:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file, nrows=5, sep=None, engine='python', encoding='latin-1')

        df = df.fillna("")
        columns_info = []
        for col in df.columns:
            dtype = "text"
            if pd.api.types.is_numeric_dtype(df[col]): dtype = "number"
            columns_info.append({"name": col, "dtype": dtype, "display_name": col, "unique_values": 0})

        return JsonResponse({
            "success": True,
            "columns": columns_info,
            "sample_rows": df.values.tolist(),
            "filename": uploaded_file.name,
            "total_rows": "Calc..."
        })
    except Exception as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)

@login_required
def import_responses_view(request: HttpRequest, public_id: str) -> HttpResponse:
    return redirect('surveys:detail', public_id=public_id)