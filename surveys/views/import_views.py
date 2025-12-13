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
from django.shortcuts import redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.apps import apps

logger = logging.getLogger(__name__)

# Intentar importar los modelos
try:
    from surveys.models import Survey, ImportJob
except ImportError:
    Survey = apps.get_model('surveys', 'Survey')
    ImportJob = apps.get_model('surveys', 'ImportJob')

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
    from surveys.tasks import process_survey_import

    if 'csv_files' in request.FILES:
        files = request.FILES.getlist('csv_files')
        jobs_data = []

        try:
            for uploaded_file in files:
                survey_title = uploaded_file.name
                new_survey = Survey.objects.create(
                    author=request.user,
                    title=survey_title,
                    description="Importación masiva desde CSV",
                    status='closed',
                    is_imported=True
                )
                file_path = _save_uploaded_csv(uploaded_file)
                job = ImportJob.objects.create(
                    survey=new_survey,
                    user=request.user,
                    csv_file=file_path,
                    original_filename=uploaded_file.name,
                    status='pending'
                )
                process_survey_import.delay(job.id)
                jobs_data.append({
                    'job_id': job.id,
                    'filename': uploaded_file.name,
                    'survey_public_id': new_survey.public_id
                })
            return JsonResponse({
                'success': True,
                'message': f'{len(jobs_data)} importaciones iniciadas.',
                'jobs': jobs_data 
            })
        except Exception as exc:
            logger.error(f"[IMPORT_BULK][ERROR] {exc}", exc_info=True)
            return JsonResponse({"success": False, "error": str(exc)}, status=500)

    elif 'csv_file' in request.FILES:
        uploaded_file = request.FILES['csv_file']
        survey_title = request.POST.get('survey_title', '').strip() or uploaded_file.name

        try:
            new_survey = Survey.objects.create(
                author=request.user,
                title=survey_title,
                description="Importada desde CSV",
                status='active',
                is_imported=True
            )
            file_path = _save_uploaded_csv(uploaded_file)
            job = ImportJob.objects.create(
                survey=new_survey,
                user=request.user,
                csv_file=file_path,
                original_filename=uploaded_file.name,
                status='pending'
            )
            process_survey_import.delay(job.id)
            return JsonResponse({
                'success': True,
                'message': 'Importación iniciada.',
                'job_id': job.id, 
                'survey_public_id': new_survey.public_id
            })
        except Exception as exc:
            logger.error(f"[IMPORT_NEW][ERROR] {exc}", exc_info=True)
            return JsonResponse({"success": False, "error": str(exc)}, status=500)
    else:
        return JsonResponse({'success': False, 'error': 'No se recibió archivo CSV.'}, status=400)

@require_POST
@csrf_exempt
@login_required
def csv_create_preview_view(request: HttpRequest) -> JsonResponse:
    if 'csv_file' not in request.FILES:
        return JsonResponse({'success': False, 'error': 'Falta archivo.'}, status=400)
    return csv_preview_view(request, public_id=None) 

# =============================================================================
# Vistas de IMPORTACIÓN EN ENCUESTA EXISTENTE (Detalle)
# =============================================================================

@require_POST
@csrf_exempt
@login_required
def csv_upload_start_import(request: HttpRequest, public_id: str) -> JsonResponse:
    from surveys.tasks import process_survey_import 

    if 'survey_file' not in request.FILES:
        return JsonResponse({'success': False, 'error': 'Falta archivo.'}, status=400)

    survey = Survey.objects.filter(public_id=public_id, author=request.user).first()
    if not survey:
        return JsonResponse({'success': False, 'error': 'Encuesta no encontrada.'}, status=404)

    uploaded_file = request.FILES['survey_file']
    
    try:
        file_path = _save_uploaded_csv(uploaded_file)
        job = ImportJob.objects.create(
            survey=survey,
            user=request.user,
            csv_file=file_path,
            original_filename=uploaded_file.name,
            status='pending'
        )
        process_survey_import.delay(job.id)
        return JsonResponse({
            'success': True, 
            'task_id': job.id,
            'job_id': job.id,
            'survey_public_id': survey.public_id 
        })
    except Exception as exc:
        logger.error(f"[IMPORT_EXISTING][ERROR] {exc}", exc_info=True)
        return JsonResponse({"success": False, "error": str(exc)}, status=500)

@require_GET
@login_required
def get_task_status_view(request: HttpRequest, task_id: int) -> JsonResponse:
    """
    Endpoint de polling para ImportJobs (basado en BD).
    Recibe un ID numérico (Primary Key de ImportJob).
    """
    try:
        job = get_object_or_404(ImportJob, id=task_id, user=request.user)
        
        response = {
            'task_id': job.id, 
            'status': job.status,
            'processed_rows': job.processed_rows,
            'total_rows': job.total_rows
        }
        
        if job.status == 'completed':
            response['result'] = {'imported_count': job.processed_rows}
        elif job.status == 'failed':
            response['error_message'] = job.error_message or job.error_log
            
        return JsonResponse(response)
    except Exception as e:
        return JsonResponse({"status": "failed", "error": str(e)}, status=500)

@require_POST
@csrf_exempt
@login_required
def csv_preview_view(request: HttpRequest, public_id: str = None) -> JsonResponse:
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
        from surveys.utils.bulk_import import _infer_column_type
        for col in df.columns:
            sample = [str(v) for v in df[col].values if v]
            dtype = _infer_column_type(col, sample)
            sample_values = list({str(v) for v in df[col].values if v})[:10]
            columns_info.append({
                "name": col,
                "dtype": dtype,
                "type": dtype,
                "display_name": col,
                "unique_values": len(set(sample)),
                "sample_values": sample_values
            })

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