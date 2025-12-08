# surveys/views/import_views.py
import io
import logging
import os
import re
import tempfile
import unicodedata

import pandas as pd
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from core.validators import CSVImportValidator
from surveys.models import ImportJob

logger = logging.getLogger(__name__)

try:
    import cpp_csv
    CPP_CSV_AVAILABLE = True
except ImportError:
    CPP_CSV_AVAILABLE = False

def _normalize_header(text):
    if not text: return ""
    s = str(text)
    s = re.sub(r"[_\-\.\[\]\(\)\{\}:]", " ", s)
    s = s.replace("¿", "").replace("?", "").replace("¡", "").replace("!", "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip().lower()

def _looks_like_timestamp(norm_name: str) -> bool:
    if not norm_name: return False
    if "marca temporal" in norm_name or "timestamp" in norm_name: return True
    tokens = norm_name.split()
    if len(tokens) <= 4 and any(kw in norm_name for kw in ["fecha", "date", "created", "creado", "submitted", "respuesta"]):
        return True
    return False

def _is_metadata_column(norm_name: str) -> bool:
    if not norm_name: return True
    STRICT_IGNORE = {"id", "pk", "uuid", "ip", "ip address", "direccion ip", "user agent", "browser", "token", "csrf", "email", "correo", "correo electronico", "source", "origen", "referer"}
    if norm_name in STRICT_IGNORE: return True
    tokens = norm_name.split()
    if "id" in tokens: return True
    user_keywords = {"usuario", "user", "username", "cuenta", "login"}
    if any(tok in user_keywords for tok in tokens): return True
    if tokens and tokens[0] == "nombre" and len(tokens) <= 3: return True
    technical_keywords = {"survey title", "survey_description", "survey description", "survey category", "question text", "question type", "option text"}
    if norm_name in technical_keywords: return True
    if norm_name.startswith("unnamed") or norm_name == "index": return True
    return False

def _classify_column(col_name: str):
    norm = _normalize_header(col_name)
    if _looks_like_timestamp(norm): return False, "Marca temporal / fecha de respuesta", "date"
    if _is_metadata_column(norm): return False, "Metadato (ID, usuario, correo, sistema…)", "meta"
    return True, "", "question"

@require_GET
@login_required
def import_job_status(request, job_id):
    try:
        log = ImportJob.objects.get(id=job_id, user=request.user)
        data = {
            "id": log.id,
            "status": log.status,
            "processed_rows": log.processed_rows,
            "total_rows": log.total_rows,
            "error_message": log.error_message,
            "survey_id": log.survey.id if log.survey else None,
        }
        return JsonResponse(data)
    except ImportJob.DoesNotExist:
        return JsonResponse({"error": "No existe el log"}, status=404)

@csrf_exempt
@login_required
@require_POST
@ratelimit(key="user", rate="20/h", method="POST", block=True)
def import_survey_csv_async(request):
    # CORRECCIÓN CRÍTICA: Importación local para evitar error circular
    from surveys.tasks import process_survey_import

    single_file = request.FILES.get("csv_file")
    multiple_files = request.FILES.getlist("csv_files")
    files_to_process = []
    if single_file: files_to_process = [single_file]
    elif multiple_files: files_to_process = multiple_files
    else: return JsonResponse({"error": "No se envió ningún archivo CSV"}, status=400)

    survey_title = request.POST.get("survey_title", "").strip() or None
    temp_dir = tempfile.gettempdir()
    job_ids = []
    errors = []

    for csv_file in files_to_process:
        try:
            CSVImportValidator.validate_csv_file(csv_file)
            fd, file_path = tempfile.mkstemp(prefix=f"import_{request.user.id}_", suffix=".csv", dir=temp_dir)
            os.close(fd)
            with open(file_path, "wb") as dest:
                for chunk in csv_file.chunks():
                    dest.write(chunk)

            log = ImportJob.objects.create(
                user=request.user,
                csv_file=file_path,
                original_filename=csv_file.name,
                survey_title=survey_title if len(files_to_process) == 1 else None,
                status="pending",
            )

            process_survey_import.delay(log.id)
            job_ids.append({"job_id": log.id, "filename": csv_file.name})

        except ValidationError as ve:
            logger.warning("[IMPORT][UPLOAD_INVALID] %s", ve)
            errors.append(f"❌ {csv_file.name}: {str(ve)}")
        except Exception as e:
            logger.error("[IMPORT][UPLOAD_ERROR] file=%s error=%s", csv_file.name, e, exc_info=True)
            errors.append(f"❌ {csv_file.name}: {str(e)}")

    if not job_ids:
        return JsonResponse({"success": False, "error": "Falló el procesamiento", "all_errors": errors}, status=400)

    if len(files_to_process) == 1:
        return JsonResponse({"success": True, "job_id": job_ids[0]["job_id"], "status": "pending"})
    else:
        return JsonResponse({"success": True, "jobs": job_ids, "errors": errors})

@login_required
@ratelimit(key="user", rate="20/h", method="POST", block=True)
def import_csv_preview_view(request):
    csv_file = request.FILES.get("csv_file")
    if not csv_file: return JsonResponse({"success": False, "error": "Falta archivo"}, status=400)
    try:
        CSVImportValidator.validate_csv_file(csv_file)
        csv_file.seek(0)
        content_bytes = csv_file.read()
        decoded_content = None
        for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try:
                decoded_content = content_bytes.decode(enc)
                break
            except UnicodeDecodeError: continue
        if decoded_content is None: return JsonResponse({"success": False, "error": "Codificación no soportada"}, status=400)
        text_buffer = io.StringIO(decoded_content)
        try: df = pd.read_csv(text_buffer, sep=None, engine="python")
        except:
            text_buffer.seek(0); 
            try: df = pd.read_csv(text_buffer, sep=",")
            except: text_buffer.seek(0); df = pd.read_csv(text_buffer, sep=";")
        if df is None or df.empty: return JsonResponse({"success": False, "error": "Archivo vacío"}, status=400)
        df = CSVImportValidator.validate_dataframe(df)
        preview = {"success": True, "filename": csv_file.name, "total_rows": int(len(df)), "total_columns": int(len(df.columns)), "columns": [], "ignored_columns": [], "sample_rows": [], "date_column": None}
        detected_date_col = None
        for col in df.columns:
            is_relevant, reason, role = _classify_column(col)
            sample = df[col].dropna()
            unique_count = int(sample.nunique())
            if role == "date" and detected_date_col is None: detected_date_col = col
            if not is_relevant:
                preview["ignored_columns"].append({"name": col, "reason": reason, "role": role})
                continue
            col_type = "text"
            sample_str = sample.astype(str)
            sample_numeric = pd.to_numeric(sample_str.str.replace(",", "."), errors="coerce")
            is_mostly_numeric = (sample_numeric.notnull().sum() > (len(sample_numeric) * 0.8) if len(sample_numeric) > 0 else False)
            lower_name = str(col).strip().lower()
            if any(k in lower_name for k in ["nps", "rating", "puntuacion"]) and is_mostly_numeric: col_type = "scale"
            elif any(k in lower_name for k in ["edad", "age", "antiguedad"]) and is_mostly_numeric: col_type = "number"
            elif is_mostly_numeric: col_type = "scale" if (sample_numeric.max() <= 10 and sample_numeric.min() >= 0) else "number"
            elif sample_str.str.contains(",").any() or sample_str.str.contains(";").any():
                if unique_count > 1: col_type = "multi"
            elif 0 < unique_count < 20: col_type = "single"
            else: col_type = "text"
            try:
                if col_type == "multi":
                    all_vals = set()
                    for v in sample_str.head(10):
                        parts = re.split(r"[;,]", v)
                        all_vals.update([p.strip() for p in parts if p.strip()])
                    sample_values = sorted(all_vals)[:5]
                else: sample_values = [str(v)[:40] for v in sample.unique()[:5]]
            except: sample_values = ["Muestra no disponible"]
            type_display = {"text": "Texto libre", "number": "Número", "scale": "Escala 0-10", "single": "Opción única", "multi": "Opción múltiple"}
            preview["columns"].append({"name": col, "display_name": str(col).replace("_", " ").strip(), "type": col_type, "type_display": type_display.get(col_type, col_type), "unique_values": unique_count, "sample_values": sample_values})
        safe_sample = df.head(5).fillna("").astype(str)
        preview["sample_rows"] = safe_sample.values.tolist()
        preview["date_column"] = detected_date_col
        return JsonResponse(preview)
    except Exception as e:
        logger.error("[IMPORT][PREVIEW_ERROR] %s", e, exc_info=True)
        return JsonResponse({"success": False, "error": f"Error interno: {str(e)}"}, status=500)

@login_required
def import_responses_view(request, public_id):
    return redirect("surveys:detail", public_id=public_id)