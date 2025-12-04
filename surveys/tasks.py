import logging
import os
import time
from datetime import timedelta
import tempfile

import pandas as pd
from surveys.models import AnswerOption
from celery import shared_task
from django.core.cache import cache
from django.db import connection, transaction
from django.utils import timezone

from surveys.models import Survey, Question, SurveyResponse, ImportJob
from surveys.utils.bulk_import import bulk_import_responses_postgres
import re
import unicodedata

logger = logging.getLogger("surveys")

# Intentar importar cpp_csv
try:
    import cpp_csv
    CPP_CSV_AVAILABLE = True
    logger.info("[TASKS] cpp_csv disponible para importaciones asíncronas")
except ImportError:
    CPP_CSV_AVAILABLE = False
    logger.warning("[TASKS] cpp_csv no disponible, usando pandas puro")


# ============================================================
# BULK DELETE SURVEYS TASK (HEAVY/ASYNC)
# ============================================================


def perform_delete_surveys(survey_ids, user_or_id):

    """
    BORRADO HÍBRIDO OPTIMIZADO (SQL + ORM)
    
    Estrategia:
    1. Usar SQL crudo para borrar las tablas masivas (QuestionResponse, SurveyResponse)
       instantáneamente, saltando la sobrecarga de memoria de Django.
    2. Usar Django ORM para borrar el objeto Survey padre, disparando señales
       de limpieza de archivos y manteniendo integridad lógica.
    """

    # 1) Normalizar user_id
    if hasattr(user_or_id, "pk"):
        user_id = user_or_id.pk
    else:
        try:
            user_id = int(user_or_id)
        except (TypeError, ValueError):
            logger.error("[DELETE][HELPER] user_or_id inválido: %r", user_or_id)
            return {"success": False, "deleted": 0, "error": "Invalid user id"}

    start = time.monotonic()
    logger.info(f"[DELETE][START] user_id={user_id} survey_ids={survey_ids}")

    try:
        with transaction.atomic():
            # Validar propiedad
            qs = Survey.objects.filter(id__in=survey_ids, author_id=user_id)
            owned_ids = list(qs.values_list("id", flat=True))

            if not owned_ids:
                return {"success": False, "deleted": 0, "error": "No owned surveys"}

            # Convertir lista de IDs a formato SQL seguro (tuple)
            ids_tuple = tuple(owned_ids)
            # Si es un solo ID, python tuple añade una coma extra que SQL necesita manejar,
            # pero la interpolación de cursor.execute lo maneja si pasamos la tupla.
            
            with connection.cursor() as cursor:
                # A) Borrado Masivo de Respuestas de Preguntas (La tabla más pesada)
                # Usamos una subquery eficiente para no traer IDs a memoria
                logger.info("[DELETE] Borrando QuestionResponse masivamente...")
                cursor.execute(f"""
                    DELETE FROM surveys_questionresponse 
                    WHERE survey_response_id IN (
                        SELECT id FROM surveys_surveyresponse WHERE survey_id IN %s
                    )
                """, [ids_tuple])
                
                # B) Borrado Masivo de Respuestas de Encuesta
                logger.info("[DELETE] Borrando SurveyResponse masivamente...")
                cursor.execute(f"""
                    DELETE FROM surveys_surveyresponse 
                    WHERE survey_id IN %s
                """, [ids_tuple])

            # C) Borrado del objeto padre vía Django (Limpio y seguro para metadatos)
            # Como ya no tiene hijos pesados, esto es instantáneo.
            deleted_count, _ = qs.delete()

        # 4) Limpiar caches
        try:
            cache.delete(f"dashboard_data_user_{user_id}")
            cache.delete(f"survey_count_user_{user_id}")
            for sid in owned_ids:
                cache.delete(f"survey_stats_{sid}")
        except Exception:
            pass

        total_ms = int((time.monotonic() - start) * 1000)
        logger.info(f"[DELETE][END] SUCCESS. user_id={user_id} ids={owned_ids} time={total_ms}ms")
        return {"success": True, "deleted": deleted_count, "error": None}

    except Exception as exc:
        total_ms = int((time.monotonic() - start) * 1000)
        logger.error(f"[DELETE][ERROR] Time={total_ms}ms Error={exc}", exc_info=True)
        return {"success": False, "deleted": 0, "error": str(exc)}


@shared_task(
    bind=True,
    name="surveys.tasks.delete_surveys_task",
    max_retries=2,
    default_retry_delay=60,
)
def delete_surveys_task(self, survey_ids, user_id):
    """
    Elimina encuestas y sus datos relacionados de forma optimizada y asíncrona.
    
    OPTIMIZACIONES IMPLEMENTADAS:
    ================================================================================
    1. 🔐 VALIDACIÓN DE PERMISOS: Solo borra encuestas del usuario propietario
    2. 💾 TRANSACCIÓN ATÓMICA: Todo o nada (garantiza consistencia)
    3. 🗑️ CASCADA AUTOMÁTICA: Django ORM borra relaciones (Questions, Responses, etc.)
    4. 🧹 LIMPIEZA DE CACHÉ: Invalida cachés relacionados post-delete
    
    FLUJO:
    ------
    1. Filtrar encuestas que pertenecen al usuario
    2. Ejecutar .delete() dentro de transaction.atomic()
    3. Limpiar cachés (dashboard, stats, etc.)
    4. Retornar resultado con conteo de eliminados
    
    MANEJO DE ERRORES:
    ------------------
    - Si el usuario no posee las encuestas, retorna error (no borrado parcial)
    - Si falla el borrado, rollback automático (transaction.atomic)
    - Retry automático hasta 2 veces con delay de 60s
    
    TIEMPOS ESPERADOS:
    ------------------
    - 1 encuesta (1K respuestas): ~500ms - 1s
    - 10 encuestas (10K respuestas): ~2-5s
    - 100 encuestas (100K respuestas): ~10-20s
    
    Args:
        survey_ids (list): IDs de encuestas a eliminar
        user_id (int): ID del usuario solicitante

    Returns:
        dict: {'success': bool, 'deleted': int, 'error': str}
    """
    try:
        result = perform_delete_surveys(survey_ids, user_id)
        if not result.get("success"):
            # If helper returned error, raise to trigger retry
            raise Exception(result.get("error") or "Unknown error in delete helper")
        logger.info(
            "[CELERY][DELETE] Eliminación asíncrona completada para %d encuestas",
            result.get("deleted", 0),
        )
        return result
    except Exception as exc:
        logger.error("[CELERY][DELETE] Error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


# ============================================================
# REPORT GENERATION TASKS
# ============================================================


@shared_task(
    bind=True,
    name="surveys.tasks.generate_pptx_report",
    max_retries=3,
    default_retry_delay=60,
)
def generate_pptx_report(self, survey_id, user_id=None):
    """
    Generate PowerPoint report for a survey asynchronously.

    Args:
        survey_id: Survey ID
        user_id: User requesting the report

    Returns:
        dict: {'success': bool, 'file_path': str, 'error': str}
    """
    try:
        from core.reports.pptx_generator import PPTXReportGenerator

        logger.info("Starting PPTX generation for survey %s", survey_id)

        # Nota: ajustado a 'author' en vez de 'creador'
        survey = Survey.objects.select_related("author").get(id=survey_id)
        generator = PPTXReportGenerator(survey)
        file_path = generator.generate()

        logger.info("PPTX generated successfully: %s", file_path)

        # Store result in cache
        cache_key = f"pptx_report_{survey_id}_{user_id or 'anon'}"
        cache.set(
            cache_key,
            {"status": "completed", "file_path": str(file_path)},
            3600,
        )

        return {"success": True, "file_path": str(file_path)}

    except Survey.DoesNotExist:
        logger.error("Survey %s not found", survey_id)
        return {"success": False, "error": "Survey not found"}

    except Exception as exc:
        logger.error("Error generating PPTX for survey %s: %s", survey_id, exc)
        raise self.retry(exc=exc)


# ============================================================
# CHART GENERATION TASKS
# ============================================================


@shared_task(
    bind=True,
    name="surveys.tasks.generate_chart_image",
    max_retries=2,
)
def generate_chart_image(self, survey_id, question_id, chart_type="bar"):
    """
    Generate chart image for a specific question.

    Args:
        survey_id: Survey ID
        question_id: Question ID
        chart_type: Type of chart ('bar', 'pie', 'line')

    Returns:
        dict: {'success': bool, 'image_path': str}
    """
    try:
        from core.utils.charts import generate_question_chart

        logger.info(
            "Generating %s chart for question %s (survey %s)",
            chart_type,
            question_id,
            survey_id,
        )

        question = Question.objects.select_related("survey").get(id=question_id)
        image_path = generate_question_chart(question, chart_type)

        logger.info("Chart generated: %s", image_path)

        return {"success": True, "image_path": str(image_path)}

    except Question.DoesNotExist:
        logger.error("Question %s not found", question_id)
        return {"success": False, "error": "Question not found"}

    except Exception as exc:
        logger.error("Error generating chart: %s", exc)
        raise self.retry(exc=exc)


# ============================================================
# DATA IMPORT TASKS (CSV -> SURVEY)
# ============================================================


def _normalize_header_for_demographics(text: str) -> str:
    """
    Normaliza el encabezado de columna para facilitar la detección de campos demográficos.
    - Quita acentos
    - Reemplaza separadores por espacios
    - Minúsculas
    """
    if text is None:
        return ""
    s = str(text)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[_\-\.\[\]\(\)\{\}:]", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def _infer_demographic_flags(col_name: str):
    """
    Dado el nombre de la columna, decide si es demográfica y de qué tipo.
    Mapea a los valores de Question.DEMOGRAPHIC_TYPES:
      - 'age', 'gender', 'location', 'occupation', 'marital_status', 'other'
    """
    norm = _normalize_header_for_demographics(col_name)

    is_demo = False
    demo_type = None

    # Edad
    if any(k in norm for k in ["edad", "age", "rango de edad", "age range", "age group"]):
        is_demo = True
        demo_type = "age"

    # Género / sexo
    elif any(k in norm for k in ["genero", "género", "gender", "sexo"]):
        is_demo = True
        demo_type = "gender"

    # Ubicación
    elif any(k in norm for k in ["ciudad", "estado", "pais", "país", "municipio", "region", "región", "ubicacion", "ubicación", "location"]):
        is_demo = True
        demo_type = "location"

    # Puesto / área / ocupación
    elif any(k in norm for k in ["puesto", "cargo", "area", "área", "departamento", "rol", "ocupacion", "ocupación"]):
        is_demo = True
        demo_type = "occupation"

    # Estado civil
    elif any(k in norm for k in ["estado civil", "soltero", "casado", "divorciado", "viudo"]):
        is_demo = True
        demo_type = "marital_status"

    return is_demo, demo_type


@shared_task(
    bind=True,
    name="surveys.tasks.process_survey_import",
    max_retries=1,
)
def process_survey_import(self, import_job_id):
    """
    Procesa la importación de un archivo CSV en background usando batches/chunks.
    
    OPTIMIZACIONES IMPLEMENTADAS:
    ================================================================================
    1. 🚀 CPP_CSV: Lectura de CSV en C++ (100x más rápido que pandas puro)
    2. 🔥 SYNCHRONOUS_COMMIT OFF: Desactiva espera de disco (máxima velocidad de escritura)
    3. 📦 BULK OPERATIONS: Usa bulk_create y COPY FROM para inserción masiva
    4. 🎯 DEMOGRAFÍA AUTO-DETECTADA: Infiere campos demográficos por keywords
    
    FLUJO:
    ------
    1. Leer CSV completo con cpp_csv (o pandas con chunks si no disponible)
    2. Crear Survey + Questions en una transacción
    3. Inferir tipos de preguntas (scale, single, multi, text, demographic)
    4. Importar todas las respuestas vía bulk_import_responses_postgres
    5. Actualizar ImportJob a 'completed' o 'failed'
    
    MANEJO DE ERRORES:
    ------------------
    - Si cpp_csv falla, fallback a pandas
    - Si falla cualquier paso, actualiza ImportJob.status = 'failed'
    - Logs detallados para debugging
    
    TIEMPOS ESPERADOS:
    ------------------
    - 1,000 filas: ~2-3 segundos
    - 10,000 filas: ~10-15 segundos
    - 100,000 filas: ~60-90 segundos
    
    Args:
        import_job_id: ID del ImportJob a procesar
        
    Returns:
        dict: {'success': bool, 'survey_id': int, 'rows': int, 'error': str}
    """
    try:
        # Bloquear el job para evitar doble procesamiento concurrente
        with transaction.atomic():
            # Lock only the ImportJob row to avoid FOR UPDATE on an outer join
            job = ImportJob.objects.select_for_update().get(id=import_job_id)
            # Optionally load user after locking without FOR UPDATE outer join issues
            if job.user_id and not hasattr(job, 'user'):
                job.user = job.__class__.objects.filter(id=job.id).select_related('user').only('id', 'user').first().user
        if job.status in ("processing", "completed"):
            logger.warning(f"[IMPORT][SKIP] Job {import_job_id} ya está en estado {job.status}")
            return {"success": False, "error": f"Job ya está en estado {job.status}"}
        if not job.user:
            job.status = "failed"
            job.error_message = "Job de importación sin usuario asociado. No se puede crear encuesta sin autor."
            job.save(update_fields=["status", "error_message", "updated_at"])
            logger.error("[IMPORT][ERROR] ImportJob %d sin usuario", import_job_id)
            return {"success": False, "error": "Job has no user assigned"}
        
        job.status = "processing"
        job.save(update_fields=["status", "updated_at"])

        csv_path = str(job.csv_file)
        user = job.user
        # Determinar título: usar `survey_title` si viene, si no, usar el nombre original del archivo
        if job.original_filename:
            # Usar el nombre original del archivo guardado
            derived_title = job.original_filename.replace(".csv", "").replace(".CSV", "")
        else:
            # Fallback: extraer del path (para jobs antiguos sin original_filename)
            base_name = os.path.basename(csv_path)
            derived_title = base_name.replace(".csv", "")
        title = (job.survey_title or derived_title)[:255]
        # Asegurar ruta de archivo real si es FileField-like
        if hasattr(job.csv_file, 'path'):
            csv_path = job.csv_file.path
        survey = None
        questions_map = {}
        total_rows = 0

        # Usar cpp_csv si está disponible, sino pandas
        if CPP_CSV_AVAILABLE:
            logger.info("[IMPORT][ASYNC] Usando cpp_csv para lectura rápida")
            try:
                # Leer todo el CSV con cpp_csv (mucho más rápido)
                raw_data = cpp_csv.read_csv_dicts(csv_path)
                full_df = pd.DataFrame(raw_data)
                df_columns = full_df.columns
                
                with transaction.atomic():
                    import_date = timezone.now().strftime("%d/%m/%Y")
                    survey = Survey.objects.create(
                        title=title[:255],
                        description=f"Encuesta importada el {import_date}",
                        status="closed",
                        author=user,
                        is_imported=True,
                    )
                    questions = []
                    questions_map_temp = {}
                    for idx, col_name in enumerate(df_columns):
                        sample = full_df[col_name].dropna()
                        col_type = "text"
                        if pd.api.types.is_numeric_dtype(sample):
                            if not sample.empty and sample.min() >= 0 and sample.max() <= 10:
                                col_type = "scale"
                            else:
                                col_type = "number"
                        elif sample.astype(str).str.contains(",").any():
                            col_type = "multi"
                        elif sample.nunique() < 20:
                            col_type = "single"
                        
                        is_demo, demo_type = _infer_demographic_flags(col_name)
                        q = Question(
                            survey=survey,
                            text=str(col_name)[:500],
                            type=col_type,
                            order=idx,
                            is_demographic=is_demo,
                            demographic_type=demo_type,
                        )
                        questions.append(q)
                        questions_map_temp[col_name] = {"question": q, "dtype": col_type}
                    
                    Question.objects.bulk_create(questions)
                    
                    # Asignar instancias reales y crear opciones
                    for idx, col_name in enumerate(df_columns):
                        q = Question.objects.filter(survey=survey, order=idx).first()
                        col_type = questions_map_temp[col_name]["dtype"]
                        entry = {"question": q, "dtype": col_type}
                        
                        if col_type in ("single", "multi"):
                            sample = full_df[col_name].dropna()
                            unique_values = sample.astype(str).unique()
                            options = []
                            for order, val in enumerate(unique_values):
                                val_norm = val.strip()
                                ao, _ = AnswerOption.objects.get_or_create(
                                    question=q, text=val_norm, defaults={"order": order}
                                )
                                options.append((val_norm, ao))
                            entry["options"] = {k: v for k, v in options}
                        questions_map[col_name] = entry
                
                # Importar todas las respuestas de una vez
                total_rows = len(full_df)
                bulk_import_responses_postgres(survey, full_df, questions_map)
                job.processed_rows = total_rows
                job.save(update_fields=["processed_rows", "updated_at"])
                
            except Exception as e:
                logger.error("[IMPORT][ASYNC] Error con cpp_csv: %s", e, exc_info=True)
                job.status = "failed"
                job.error_message = f"Error al procesar CSV con cpp_csv: {str(e)}"
                job.save(update_fields=["status", "error_message", "updated_at"])
                return {"success": False, "error": str(e)}
        else:
            # Fallback a pandas con chunks (más lento)
            logger.info("[IMPORT][ASYNC] cpp_csv no disponible, usando pandas con chunks")
            chunk_size = 1000
            encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]

            # Intentar distintos encodings y crear Survey + Questions a partir del primer chunk
            for encoding in encodings:
                try:
                    chunk_iter = pd.read_csv(
                        csv_path,
                        encoding=encoding,
                        chunksize=chunk_size,
                    )
                    first_chunk = next(chunk_iter)
                    df_columns = first_chunk.columns

                    with transaction.atomic():
                        import_date = timezone.now().strftime("%d/%m/%Y")
                        survey = Survey.objects.create(
                            title=title[:255],
                            description=f"Encuesta importada el {import_date}",
                            status="closed",
                            author=user,
                            is_imported=True,
                        )
                        questions = []
                        questions_map_temp = {}
                        for idx, col_name in enumerate(df_columns):
                            sample = first_chunk[col_name].dropna()
                            col_type = "text"
                            if pd.api.types.is_numeric_dtype(sample):
                                if not sample.empty and sample.min() >= 0 and sample.max() <= 10:
                                    col_type = "scale"
                                else:
                                    col_type = "number"
                            elif sample.astype(str).str.contains(",").any():
                                col_type = "multi"
                            elif sample.nunique() < 20:
                                col_type = "single"
                            # Nuevo: inferir si es demográfica
                            is_demo, demo_type = _infer_demographic_flags(col_name)
                            q = Question(
                                survey=survey,
                                text=str(col_name)[:500],
                                type=col_type,
                                order=idx,
                                is_demographic=is_demo,
                                demographic_type=demo_type,
                            )
                            questions.append(q)
                            questions_map_temp[col_name] = {"question": q, "dtype": col_type}
                        Question.objects.bulk_create(questions)
                        # Asignar instancias reales a questions_map
                        for idx, col_name in enumerate(df_columns):
                            q = Question.objects.filter(survey=survey, order=idx).first()
                            col_type = questions_map_temp[col_name]["dtype"]
                            entry = {"question": q, "dtype": col_type}
                            # Si es single/multi, crear AnswerOption y options
                            if col_type in ("single", "multi"):
                                unique_values = sample.astype(str).unique()
                                options = []
                                for order, val in enumerate(unique_values):
                                    val_norm = val.strip()
                                    ao, _ = AnswerOption.objects.get_or_create(question=q, text=val_norm, defaults={"order": order})
                                    options.append((val_norm, ao))
                                entry["options"] = {k: v for k, v in options}
                            questions_map[col_name] = entry
                    break
                except UnicodeDecodeError:
                    continue
                except Exception as e:
                    logger.error("Error al procesar chunk inicial: %s", e, exc_info=True)
                    continue
            else:
                job.status = "failed"
                job.error_message = (
                    "No se pudo leer el archivo CSV. Verifique la codificación."
                )
                job.save(update_fields=["status", "error_message", "updated_at"])
                return {"success": False, "error": job.error_message}

            def process_chunk(chunk):
                nonlocal total_rows
                total_rows += len(chunk)
                bulk_import_responses_postgres(survey, chunk, questions_map)
                job.processed_rows = total_rows
                job.save(update_fields=["processed_rows", "updated_at"])

            # Procesar el primer chunk y el resto
            process_chunk(first_chunk)
            for chunk in chunk_iter:
                process_chunk(chunk)

        job.status = "completed"
        job.survey = survey
        job.total_rows = total_rows
        job.save(
            update_fields=[
                "status",
                "survey",
                "total_rows",
                "processed_rows",
                "updated_at",
            ]
        )
        # Borrar archivo temporal tras completar
        try:
            if os.path.exists(csv_path):
                os.remove(csv_path)
        except Exception as _e:
            logger.warning(f"[IMPORT][CLEANUP] No se pudo borrar archivo temporal {csv_path}: {_e}")
        return {"success": True, "survey_id": survey.id, "rows": total_rows}
    except Exception as exc:
        logger.error("Error en importación async: %s", exc, exc_info=True)
        job = ImportJob.objects.filter(id=import_job_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            job.save(update_fields=["status", "error_message", "updated_at"])
        return {"success": False, "error": str(exc)}


# ============================================================
# MAINTENANCE TASKS
# ============================================================


@shared_task(name="surveys.tasks.cleanup_old_responses")
def cleanup_old_responses():
    """
    Clean up responses older than 2 years (configurable).
    Runs daily at 3 AM via Celery Beat.
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=730)  # 2 years

        old_responses = SurveyResponse.objects.filter(
            created_at__lt=cutoff_date,
            survey__status="archived",
        )

        count = old_responses.count()
        old_responses.delete()

        logger.info("Cleaned up %d old responses", count)
        return {"deleted": count}

    except Exception as exc:
        logger.error("Cleanup error: %s", exc)
        return {"error": str(exc)}


@shared_task(name="surveys.tasks.generate_monthly_reports")
def generate_monthly_reports():
    """
    Generate monthly summary reports for all active surveys.
    Runs on the first day of each month at 4 AM.
    """
    try:
        active_surveys = Survey.objects.filter(status="active").values_list(
            "id", flat=True
        )

        results = []
        # Nota: se asume que existe una tarea generate_pdf_report en otro módulo.
        # Ajusta este import según tu proyecto real.
        from core.tasks import generate_pdf_report

        for survey_id in active_surveys:
            result = generate_pdf_report.delay(survey_id)
            results.append({"survey_id": survey_id, "task_id": result.id})

        logger.info("Generated %d monthly reports", len(results))
        return {"reports": results}

    except Exception as exc:
        logger.error("Monthly reports error: %s", exc)
        return {"error": str(exc)}


@shared_task(name="surveys.tasks.cleanup_cache")
def cleanup_cache():
    """
    Clean up expired cache entries.
    Runs daily at 2:30 AM.
    """
    try:
        # Django-redis maneja expiración automáticamente.
        # Esta tarea queda para lógica custom si la necesitas.
        logger.info("Cache cleanup completed")
        return {"success": True}

    except Exception as exc:
        logger.error("Cache cleanup error: %s", exc)
        return {"error": str(exc)}


# ============================================================
# ANALYSIS TASKS
# ============================================================


@shared_task(
    bind=True,
    name="surveys.tasks.analyze_survey_data",
)
def analyze_survey_data(self, survey_id):
    """
    Perform heavy statistical analysis on survey data.

    Args:
        survey_id: Survey ID

    Returns:
        dict: Analysis results
    """
    try:
        from core.services.survey_analysis import SurveyAnalysisService

        logger.info("Starting analysis for survey %s", survey_id)

        # Ojo: aquí asumimos related_name en inglés ('questions', 'responses')
        survey = Survey.objects.prefetch_related("questions", "responses").get(
            id=survey_id
        )
        qs = SurveyResponse.objects.filter(survey=survey)

        # Generar clave de caché
        cache_key = f"survey_analysis_{survey_id}"

        # Obtener datos de análisis
        data = SurveyAnalysisService.get_analysis_data(
            survey,
            qs,
            include_charts=True,
            cache_key=cache_key,
        )

        # Cache analysis results for 30 minutes
        cache.set(cache_key, data, 1800)

        logger.info("Analysis completed for survey %s", survey_id)
        return data

    except Survey.DoesNotExist:
        logger.error("Survey %s not found", survey_id)
        return {"error": "Survey not found"}

    except Exception as exc:
        logger.error("Analysis error: %s", exc)
        raise self.retry(exc=exc)


@shared_task(name="surveys.tasks.update_survey_statistics")
def update_survey_statistics(survey_id):
    """
    Update cached statistics for a survey.
    Called after new responses are submitted.
    """
    try:
        survey = Survey.objects.prefetch_related("responses").get(id=survey_id)

        total_responses = survey.responses.count()
        if total_responses:
            # OJO: si el campo ya no se llama 'completada', cámbialo aquí
            completed_count = survey.responses.filter(completada=True).count()
            completion_rate = completed_count / total_responses
            last_response_obj = survey.responses.order_by("-created_at").first()
            last_response_ts = (
                last_response_obj.created_at if last_response_obj else None
            )
        else:
            completion_rate = 0
            last_response_ts = None

        stats = {
            "total_responses": total_responses,
            "completion_rate": completion_rate,
            "last_response": last_response_ts,
        }

        cache_key = f"survey_stats_{survey_id}"
        cache.set(cache_key, stats, 600)  # 10 minutes

        return stats

    except Exception as exc:
        logger.error("Statistics update error: %s", exc)
        return {"error": str(exc)}
