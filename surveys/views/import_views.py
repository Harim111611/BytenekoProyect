import logging
import os
import tempfile
import time
import re
import unicodedata
from datetime import datetime

import pandas as pd
from django.contrib import messages

try:
    import cpp_csv
    CPP_CSV_AVAILABLE = True
    logging.info("[IMPORT] Usando cpp_csv para lectura rápida")
except ImportError:
    CPP_CSV_AVAILABLE = False
    logging.warning("[IMPORT] Módulo cpp_csv no disponible, usando Pandas puro (más lento)")
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from core.validators import CSVImportValidator
from surveys.models import Survey, Question, AnswerOption, ImportJob
from surveys.tasks import process_survey_import
from surveys.utils.bulk_import import bulk_import_responses_postgres

# Si usas el decorador de performance, asegúrate que existe en core.utils.logging_utils
try:
    from core.utils.logging_utils import log_performance
except ImportError:
    # Fallback dummy decorator si no existe
    def log_performance(**kwargs):
        def decorator(func):
            return func
        return decorator

logger = logging.getLogger(__name__)


# ============================================================
# UTILS: NORMALIZACIÓN Y DETECCIÓN (Sincronizado con Analysis)
# ============================================================

def _normalize_text(text):
    """Normalización agresiva para análisis semántico (igual que en survey_analysis)."""
    if not text:
        return ''
    text_str = str(text)
    # Separar CamelCase
    text_str = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text_str)
    # Limpiar caracteres especiales
    text_str = re.sub(r'[_\-\.\[\]\(\)\{\}:]', ' ', text_str)
    text_str = text_str.replace('¿', '').replace('?', '').replace('¡', '').replace('!', '')
    # Normalizar ASCII
    normalized = unicodedata.normalize('NFKD', text_str).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', normalized).strip().lower()

def _is_column_relevant(col_name):
    """
    Determina si una columna es relevante como Pregunta o si debe ser ignorada/tratada como metadato.
    Retorna: (es_relevante: bool, razon: str)
    """
    normalized = _normalize_text(col_name)
    
    # 1. FECHAS Y METADATOS TEMPORALES
    DATE_KEYWORDS = [
        'fecha', 'date', 'created', 'creado', 'timestamp', 'hora', 'time', 
        'nacimiento', 'birth', 'start', 'end', 'inicio', 'fin', 'started', 'ended',
        'periodo', 'period', 'mes', 'month', 'anio', 'year', 'submitted', 'envio'
    ]

    # 2. IDENTIFICADORES DE USUARIO Y PII (LISTA COMPLETA)
    IDENTIFIER_KEYWORDS = [
        # Identidad directa
        'nombre', 'name', 'apellido', 'lastname', 'surname', 'fullname', 'full name',
        'correo', 'email', 'mail', 'e-mail', 'direccion', 'address',
        # Contacto
        'telefono', 'tel', 'phone', 'celular', 'mobile', 'movil', 'whatsapp',
        # Documentos de Identidad
        'id', 'identificacion', 'identification', 'documento', 'dni', 'curp', 'rfc', 'cedula', 
        'passport', 'pasaporte', 'ssn', 'matricula', 'legajo',
        # Huella Digital / Técnica del Usuario
        'ip', 'ip_address', 'ip address', 'direccion ip', 'mac address',
        'user_agent', 'user agent', 'browser', 'navegador', 'dispositivo', 'device',
        'uuid', 'guid', 'token', 'session', 'cookie', 'user', 'usuario', 'login',
        # Datos Transaccionales
        'reserva', 'booking', 'ticket', 'folio', 'transaction', 'transaccion',
        'latitud', 'latitude', 'longitud', 'longitude', 'geo'
    ]

    # 3. METADATOS TÉCNICOS DE LA ENCUESTA
    METADATA_KEYWORDS = [
        'survey', 'encuesta', 'title', 'titulo', 'status', 'estado', 
        'network', 'red', 'referer', 'source', 'origen', 'channel', 'canal',
        'campaign', 'campana', 'medium', 'medio',
        'submit', 'enviado', 'completed', 'completado', 'time taken', 'tiempo tomado',
        'language', 'idioma'
    ]

    def contains_keyword(text, kw):
        if ' ' in kw: return kw in text
        return re.search(r'\b' + re.escape(kw) + r'\b', text) is not None

    if any(contains_keyword(normalized, kw) for kw in DATE_KEYWORDS):
        return False, "Campo temporal/fecha"
    
    if any(contains_keyword(normalized, kw) for kw in IDENTIFIER_KEYWORDS):
        return False, "Dato personal o identificador único"
        
    if any(contains_keyword(normalized, kw) for kw in METADATA_KEYWORDS):
        return False, "Metadato técnico de encuesta"

    return True, ""


# ============================================================
# ENDPOINT ASÍNCRONO: ESTADO DEL IMPORT
# ============================================================

@require_GET
@login_required
def import_job_status(request, job_id):
    """
    Devuelve el estado de un ImportJob en JSON para el frontend.
    """
    try:
        job = ImportJob.objects.get(id=job_id, user=request.user)
        data = {
            "id": job.id,
            "status": job.status,
            "processed_rows": job.processed_rows,
            "total_rows": job.total_rows,
            "error_message": job.error_message,
            "survey_id": job.survey.id if job.survey else None,
        }
        return JsonResponse(data)
    except ImportJob.DoesNotExist:
        return JsonResponse({"error": "No existe el job"}, status=404)


# ============================================================
# VISTA UNIFICADA: IMPORTACIÓN ASÍNCRONA VÍA CELERY
# ============================================================

@csrf_exempt
@login_required
@require_POST
@ratelimit(key="user", rate="20/h", method="POST", block=True)
def import_survey_csv_async(request):
    """
    Vista unificada para importación de CSV con Celery.
    Soporta:
    - Un archivo único (csv_file)
    - Múltiples archivos (csv_files)
    - Título personalizado opcional (survey_title)
    
    TODO EL PROCESAMIENTO SE HACE EN CELERY - EL SERVIDOR RESPONDE EN < 200ms.
    """
    # Detectar si es importación única o múltiple
    single_file = request.FILES.get("csv_file")
    multiple_files = request.FILES.getlist("csv_files")
    
    files_to_process = []
    if single_file:
        files_to_process = [single_file]
    elif multiple_files:
        files_to_process = multiple_files
    else:
        return JsonResponse({"error": "No se envió ningún archivo CSV"}, status=400)
    
    # Validar límites
    if len(files_to_process) > 10:
        return JsonResponse({"success": False, "error": "Máximo 10 archivos permitidos"}, status=400)

    # Obtener título personalizado (solo para archivo único)
    survey_title = request.POST.get("survey_title", "").strip() or None

    # Guardado en directorio temporal del sistema (más seguro)
    temp_dir = tempfile.gettempdir()
    
    job_ids = []
    errors = []
    
    for csv_file in files_to_process:
        try:
            # Guardar archivo en disco
            # Crear archivo temporal único
            fd, file_path = tempfile.mkstemp(prefix=f"import_{request.user.id}_", suffix=".csv", dir=temp_dir)
            os.close(fd)
            with open(file_path, "wb") as dest:
                for chunk in csv_file.chunks():
                    dest.write(chunk)
            
            # Crear ImportJob
            job = ImportJob.objects.create(
                user=request.user,
                csv_file=file_path,
                original_filename=csv_file.name,
                survey_title=survey_title if len(files_to_process) == 1 else None,
                status="pending",
            )
            
            # 🚀 LANZAR TAREA CELERY (trabajo pesado en background)
            process_survey_import.delay(job.id)
            
            job_ids.append({"job_id": job.id, "filename": csv_file.name})
            
        except Exception as e:
            logger.error(f"[IMPORT][UPLOAD_ERROR] file={csv_file.name} error={e}")
            errors.append(f"❌ {csv_file.name}: {str(e)}")
    
    # Validar que al menos un archivo se procesó
    if not job_ids:
        return JsonResponse({
            "success": False, 
            "error": "No se pudo procesar ningún archivo", 
            "all_errors": errors
        }, status=400)
    
    # Respuesta rápida (< 200ms) - El trabajo pesado está en Celery
    if len(files_to_process) == 1:
        # Respuesta para archivo único (compatibilidad con código existente)
        return JsonResponse({
            "success": True,
            "job_id": job_ids[0]["job_id"], 
            "status": "pending"
        })
    else:
        # Respuesta para múltiples archivos
        return JsonResponse({
            "success": True, 
            "jobs": job_ids, 
            "errors": errors
        })


# Alias para compatibilidad con código existente
import_multiple_surveys_view = import_survey_csv_async


@login_required
@ratelimit(key="user", rate="20/h", method="POST", block=True)
def import_csv_preview_view(request):
    """
    Genera una vista previa INTELIGENTE: Filtra columnas irrelevantes (fechas, IDs)
    para mostrar solo lo que se convertirá en preguntas de análisis.
    """
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"success": False, "error": "Falta archivo"}, status=400)

    try:
        CSVImportValidator.validate_csv_file(csv_file)
        encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
        df = None
        for encoding in encodings:
            try:
                csv_file.seek(0)
                df = pd.read_csv(csv_file, encoding=encoding)
                break
            except Exception: continue

        if df is None: return JsonResponse({"success": False, "error": "Archivo ilegible"}, status=400)

        df = CSVImportValidator.validate_dataframe(df)

        preview = {
            "success": True,
            "filename": csv_file.name,
            "total_rows": len(df),
            "total_columns": len(df.columns),
            "columns": [],
            "ignored_columns": [],
            "sample_rows": [],
        }

        # --- FILTRADO INTELIGENTE DE COLUMNAS ---
        for col in df.columns:
            # 1. Determinar relevancia
            is_relevant, reason = _is_column_relevant(col)
            
            sample = df[col].dropna()
            
            if not is_relevant:
                preview["ignored_columns"].append({
                    "name": col,
                    "reason": reason
                })
                continue

            # 2. Si es relevante, determinamos el tipo para el preview
            col_type = "text"
            unique_count = sample.nunique()
            sample_values = []
            avg_len = sample.astype(str).map(len).mean() if not sample.empty else 0

            lower_name = str(col).strip().lower()
            
            # Mismas reglas mejoradas que en el importador real
            if any(k in lower_name for k in ["nps", "recomendacion", "recomendar", "satisfaccion", "rating"]):
                col_type = "scale"
                sample_values = [str(int(v)) for v in sorted(sample.unique()[:10])] if not sample.empty else []
            elif any(k in lower_name for k in ["edad", "age", "antiguedad"]):
                col_type = "number"
                sample_values = [str(v) for v in sample.unique()[:5]]
            elif any(k in lower_name for k in ["comentario", "sugerencia", "opinion", "observacion", "feedback"]):
                col_type = "text" # FORCE TEXT
                sample_values = [str(v)[:50] + '...' for v in sample.unique()[:3]]
            else:
                if pd.api.types.is_numeric_dtype(sample):
                    if not sample.empty and sample.min() >= 0 and sample.max() <= 10:
                        col_type = "scale"
                        sample_values = [str(int(v)) for v in sorted(sample.unique()[:10])]
                    else:
                        col_type = "number"
                        sample_values = [str(v) for v in sample.unique()[:5]]
                elif sample.astype(str).str.contains(",").any():
                    col_type = "multi"
                    all_options = set()
                    for val in sample.astype(str):
                        if val and val.lower() not in ['nan', 'none', '']:
                            all_options.update([p.strip() for p in val.split(',')])
                    sample_values = sorted(list(all_options))[:10]
                # Solo clasificar como single si es corto y repetitivo
                elif unique_count < 20 and unique_count > 1 and avg_len < 30:
                    col_type = "single"
                    sample_values = [str(v) for v in sample.unique()[:10]]
                else:
                    col_type = "text"
                    sample_values = [str(v)[:50] + '...' if len(str(v)) > 50 else str(v) for v in sample.unique()[:3]]

            type_display = {
                "text": "Texto libre",
                "number": "Número",
                "scale": "Escala 1-10",
                "single": "Opción única",
                "multi": "Opción múltiple"
            }

            preview["columns"].append({
                "name": col,
                "display_name": col.replace("_", " ").title(),
                "type": col_type,
                "type_display": type_display.get(col_type, col_type),
                "unique_values": unique_count if col_type != "multi" else len(sample_values),
                "sample_values": sample_values,
            })

        preview["sample_rows"] = df.head(5).astype(object).where(pd.notnull(df), "").astype(str).values.tolist()

        return JsonResponse(preview)

    except Exception as e:
        logger.error(f"[IMPORT][PREVIEW_ERROR] {e}", exc_info=True)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def import_responses_view(request, public_id):
    """Placeholder para importar respuestas a una encuesta existente"""
    return redirect("surveys:detail", public_id=public_id)