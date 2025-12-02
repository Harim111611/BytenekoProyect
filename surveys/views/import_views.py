import logging
import os
import time
from datetime import datetime

import pandas as pd
from django.contrib import messages
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
# VISTA ASÍNCRONA: CREA IMPORTJOB Y LANZA CELERY
# ============================================================

@csrf_exempt
@login_required
@require_POST
def import_survey_csv_async(request):
    """
    Recibe un archivo CSV, crea ImportJob, guarda el archivo y lanza la tarea Celery.
    """
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        return JsonResponse({"error": "No se envió archivo CSV"}, status=400)

    # Guardar archivo en disco (carpeta temporal segura)
    upload_dir = os.path.join("data", "import_jobs")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(
        upload_dir,
        f"import_{request.user.id}_{int(time.time())}.csv"
    )

    with open(file_path, "wb+") as dest:
        for chunk in csv_file.chunks():
            dest.write(chunk)

    # Crear ImportJob
    job = ImportJob.objects.create(
        user=request.user,
        csv_file=file_path,
        status="pending",
    )

    # Lanzar tarea Celery
    process_survey_import.delay(job.id)

    return JsonResponse({"job_id": job.id, "status": job.status})


# ============================================================
# HELPER INTERNO: PROCESAR UN SOLO CSV (SIN CELERY)
# ============================================================

def _process_single_csv_import(csv_file, user, override_title=None):
    """
    Lógica central para procesar un archivo CSV y crear una encuesta.
    Retorna (Survey, rows_count, answers_count) o lanza Exception.
    """
    # 1. Validar archivo
    CSVImportValidator.validate_csv_file(csv_file)

    # 2. Leer CSV en modo batch/chunksize para evitar cargar todo en memoria
    encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
    chunk_size = 1000  # Ajustable según RAM/disco
    df_columns = None
    survey = None
    questions_map = {}
    total_rows = 0
    title = (
        override_title
        if override_title
        else csv_file.name.replace(".csv", "").replace("_", " ").title()
    )

    t0 = time.perf_counter()
    # Intentar distintos encodings
    for encoding in encodings:
        try:
            csv_file.seek(0)
            chunk_iter = pd.read_csv(csv_file, encoding=encoding, chunksize=chunk_size)
            first_chunk = next(chunk_iter)
            df_columns = first_chunk.columns
            CSVImportValidator.validate_dataframe(first_chunk)
            with transaction.atomic():
                survey = Survey.objects.create(
                    title=title[:255],
                    description=f"Importado automáticamente desde {csv_file.name}",
                    status="closed",  # Las encuestas importadas siempre están cerradas
                    author=user,
                    is_imported=True,  # Marcar como importada
                )
                questions = []
                questions_map_temp = {}
                for idx, col_name in enumerate(df_columns):
                    sample = first_chunk[col_name].dropna()
                    col_type = "text"
                    
                    # Detectar tipo de pregunta según los datos
                    if pd.api.types.is_numeric_dtype(sample):
                        # Si todos los valores están entre 0-10, es una escala
                        if not sample.empty and sample.min() >= 0 and sample.max() <= 10:
                            col_type = "scale"
                        else:
                            col_type = "number"
                    elif sample.astype(str).str.contains(",").any():
                        # Si contiene comas, probablemente sea multi-opción
                        col_type = "multi"
                    elif sample.nunique() < 20 and sample.nunique() > 1:
                        # Si tiene pocas opciones únicas (menos de 20), es opción única
                        col_type = "single"
                    
                    q = Question(
                        survey=survey,
                        text=col_name[:500],
                        type=col_type,
                        order=idx,
                    )
                    questions.append(q)
                    questions_map_temp[col_name] = {
                        "question": q, 
                        "dtype": col_type,
                        "sample": sample  # Guardar sample para usar después
                    }
                
                Question.objects.bulk_create(questions)
                
                # Crear opciones para preguntas de tipo single/multi
                for idx, col_name in enumerate(df_columns):
                    q = Question.objects.filter(survey=survey, order=idx).first()
                    temp_data = questions_map_temp[col_name]
                    col_type = temp_data["dtype"]
                    sample = temp_data["sample"]
                    
                    entry = {"question": q, "dtype": col_type}
                    
                    if col_type == "multi":
                        # Para multi-opción, extraer todas las opciones individuales separadas por comas
                        all_options = set()
                        for val in sample.astype(str):
                            if val and val.lower() not in ['nan', 'none', '']:
                                # Separar por comas y limpiar cada opción
                                parts = [p.strip() for p in val.split(',')]
                                all_options.update(parts)
                        
                        # Crear las opciones individuales
                        options = []
                        for order, opt_text in enumerate(sorted(all_options)):
                            if opt_text:
                                ao, _ = AnswerOption.objects.get_or_create(
                                    question=q, 
                                    text=opt_text, 
                                    defaults={"order": order}
                                )
                                options.append((opt_text, ao))
                        entry["options"] = {k: v for k, v in options}
                        
                    elif col_type == "single":
                        # Para single, cada valor único es una opción
                        unique_values = sample.astype(str).unique()
                        options = []
                        for order, val in enumerate(unique_values):
                            if val and val.lower() not in ['nan', 'none', '']:
                                val_norm = val.strip()
                                ao, _ = AnswerOption.objects.get_or_create(
                                    question=q, 
                                    text=val_norm, 
                                    defaults={"order": order}
                                )
                                options.append((val_norm, ao))
                        entry["options"] = {k: v for k, v in options}
                    
                    questions_map[col_name] = entry
            break
        except UnicodeDecodeError:
            continue
        except Exception as e:
            logger.error(f"[IMPORT][ERROR][INIT] file={csv_file.name} error={str(e)}", exc_info=True)
            continue
    else:
        raise ValidationError(f"No se pudo leer el archivo {csv_file.name}. Verifique la codificación.")

    answers_count = 0
    # --- Detectar columna de fecha automáticamente ---
    DATE_KEYWORDS = ['fecha', 'date', 'created', 'creado', 'timestamp', 'hora', 'time']
    date_candidates = [col for col in df_columns if any(kw in col.lower() for kw in DATE_KEYWORDS)]
    date_column = None
    if len(date_candidates) == 1:
        date_column = date_candidates[0]
    elif len(date_candidates) > 1:
        # Aquí se puede implementar lógica para que el usuario elija, por ahora tomamos la primera
        # TODO: Permitir selección de columna de fecha en el frontend
        date_column = date_candidates[0]
    # Si no hay ninguna, date_column queda en None y se usará la fecha de importación

    def process_chunk(chunk):
        nonlocal total_rows, answers_count
        total_rows += len(chunk)
        res = bulk_import_responses_postgres(survey, chunk, questions_map, date_column=date_column)
        if isinstance(res, tuple):
            _, ac = res
            answers_count += ac
        else:
            answers_count += 0

    logger.info(f"[IMPORT][START] file={csv_file.name}")
    process_chunk(first_chunk)
    for chunk in chunk_iter:
        process_chunk(chunk)
    t1 = time.perf_counter()
    logger.info(f"[IMPORT][END] file={csv_file.name} survey_id={survey.id if survey else None} rows={total_rows} time={t1-t0:.2f}s")
    return survey, total_rows, answers_count


# ============================================================
# VISTAS SINCRÓNICAS (FLUJO ANTERIOR)
# ============================================================

from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
@login_required
@require_POST
@ratelimit(key="user", rate="10/h", method="POST", block=True)
@log_performance(threshold_ms=5000)
def import_survey_view(request):
    """
    Importa un único archivo CSV.
    Retorna JSON para integración con el frontend.
    """
    try:
        if request.method != "POST":
            return JsonResponse({"success": False, "error": "Método no permitido"}, status=405)

        csv_file = request.FILES.get("csv_file", None)
        survey_title = request.POST.get("survey_title")

        if not csv_file:
            return JsonResponse(
                {"success": False, "error": "No se recibió ningún archivo."},
                status=400,
            )

        max_size_mb = 10
        if csv_file.size > max_size_mb * 1024 * 1024:
            return JsonResponse(
                {
                    "success": False,
                    "error": f"El archivo es demasiado grande, límite: {max_size_mb} MB.",
                },
                status=400,
            )

        survey, rows, _ = _process_single_csv_import(csv_file, request.user, survey_title)
        logger.info(f"[IMPORT] file={csv_file.name} encuestas=1 respuestas={rows}")
        messages.success(
            request,
            f"¡Éxito! Encuesta '{survey.title}' creada con {rows} respuestas.",
        )
        from django.urls import reverse
        return JsonResponse(
            {
                "success": True,
                "redirect_url": reverse("surveys:results", args=[survey.id]),
            }
        )
    except ValidationError as e:
        csv_file = locals().get('csv_file', None)
        logger.warning(f"[IMPORT][VALIDATION] file={getattr(csv_file, 'name', '')} error={str(e)}")
        return JsonResponse({"success": False, "error": str(e)}, status=400)
    except Exception as e:
        csv_file = locals().get('csv_file', None)
        logger.error(
            f"[IMPORT][ERROR] file={getattr(csv_file, 'name', '')} error={str(e)}",
            exc_info=True,
        )
        return JsonResponse(
            {"success": False, "error": f"Error interno: {str(e)}"},
            status=500,
        )


@login_required
@require_POST
@ratelimit(key="user", rate="20/h", method="POST", block=True)
def import_multiple_surveys_view(request):
    """
    Importa múltiples archivos CSV a la vez.
    """
    files = request.FILES.getlist("csv_files")
    if not files:
        return JsonResponse(
            {"success": False, "error": "No se recibieron archivos."},
            status=400,
        )

    max_size_mb = 10
    results = []
    errors = []
    success_count = 0

    for csv_file in files:
        if csv_file.size > max_size_mb * 1024 * 1024:
            msg = f"Archivo {csv_file.name} demasiado grande (> {max_size_mb} MB)"
            logger.warning(f"[IMPORT][VALIDATION] file={csv_file.name} error=too_large")
            errors.append(f"❌ {csv_file.name}: {msg}")
            continue
        try:
            survey, rows, _ = _process_single_csv_import(csv_file, request.user)
            logger.info(f"[IMPORT] file={csv_file.name} encuestas=1 respuestas={rows}")
            results.append(f"✅ {csv_file.name}: {rows} respuestas")
            success_count += 1
        except ValidationError as e:
            logger.warning(
                f"[IMPORT][VALIDATION] file={csv_file.name} error={str(e)}"
            )
            errors.append(f"❌ {csv_file.name}: {str(e)}")
        except Exception as e:
            logger.error(f"[IMPORT][ERROR] file={csv_file.name} error={str(e)}")
            errors.append(f"❌ {csv_file.name}: Error interno")

    if success_count > 0:
        msg = f"Se importaron {success_count} encuesta(s) correctamente."
        messages.success(request, msg)
    if errors:
        messages.warning(
            request,
            "Hubo errores en algunos archivos. Revisa el reporte.",
        )

    return JsonResponse(
        {
            "success": success_count > 0,
            "imported_count": success_count,
            "all_errors": errors,
            "details": results,
        }
    )


@login_required
@ratelimit(key="user", rate="20/h", method="POST", block=True)
def import_csv_preview_view(request):
    """
    Genera una vista previa de la estructura del CSV sin guardar nada en BD.
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
            except Exception:
                continue

        if df is None:
            return JsonResponse(
                {"success": False, "error": "Archivo ilegible"},
                status=400,
            )

        df = CSVImportValidator.validate_dataframe(df)

        preview = {
            "success": True,
            "filename": csv_file.name,
            "total_rows": len(df),
            "total_columns": len(df.columns),
            "columns": [],
            "sample_rows": [],
        }

        for col in df.columns:
            sample = df[col].dropna()
            col_type = "text"
            unique_count = sample.nunique()
            sample_values = []

            # Detectar tipo de pregunta según los datos
            if pd.api.types.is_numeric_dtype(sample):
                # Si todos los valores están entre 0-10, es una escala
                if not sample.empty and sample.min() >= 0 and sample.max() <= 10:
                    col_type = "scale"
                    sample_values = [str(int(v)) for v in sorted(sample.unique()[:10])]
                else:
                    col_type = "number"
                    sample_values = [str(v) for v in sample.unique()[:5]]
            elif sample.astype(str).str.contains(",").any():
                # Si contiene comas, probablemente sea multi-opción
                col_type = "multi"
                # Extraer opciones individuales
                all_options = set()
                for val in sample.astype(str):
                    if val and val.lower() not in ['nan', 'none', '']:
                        parts = [p.strip() for p in val.split(',')]
                        all_options.update(parts)
                sample_values = sorted(list(all_options))[:10]
            elif unique_count < 20 and unique_count > 1:
                # Si tiene pocas opciones únicas (menos de 20 y más de 1), es opción única
                col_type = "single"
                sample_values = [str(v) for v in sample.unique()[:10] if str(v).lower() not in ['nan', 'none', '']]
            else:
                # Texto libre
                sample_values = [str(v)[:50] + '...' if len(str(v)) > 50 else str(v) for v in sample.unique()[:3] if str(v).lower() not in ['nan', 'none', '']]

            # Mapeo de tipos a nombres legibles en español
            type_display = {
                "text": "Texto libre",
                "number": "Número",
                "scale": "Escala 1-10",
                "single": "Opción única",
                "multi": "Opción múltiple"
            }

            preview["columns"].append(
                {
                    "name": col,
                    "display_name": col.replace("_", " ").title(),
                    "type": col_type,
                    "type_display": type_display.get(col_type, col_type),
                    "unique_values": unique_count if col_type != "multi" else len(sample_values),
                    "sample_values": sample_values,
                }
            )

        preview["sample_rows"] = (
            df.head(5)
            .astype(object)
            .where(pd.notnull(df), "")
            .astype(str)
            .values
            .tolist()
        )

        return JsonResponse(preview)

    except Exception as e:
        logger.error(f"[IMPORT][PREVIEW_ERROR] {e}", exc_info=True)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def import_responses_view(request, pk):
    """Placeholder para importar respuestas a una encuesta existente"""
    return redirect("surveys:detail", pk=pk)
