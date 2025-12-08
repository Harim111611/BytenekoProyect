# surveys/tasks.py
import logging
import os
import re
import unicodedata

import pandas as pd
from celery import shared_task
from django.db import connection, transaction
from django.utils import timezone

# Asegúrate de que las importaciones a tus modelos están aquí
from surveys.models import Survey, Question, SurveyResponse, ImportJob, AnswerOption
from surveys.utils.bulk_import import bulk_import_responses_postgres

logger = logging.getLogger("surveys")

try:
    import cpp_csv
    CPP_CSV_AVAILABLE = True
except ImportError:
    CPP_CSV_AVAILABLE = False

# Las funciones helper (normalize_header, etc.) van aquí. Omitidas por brevedad.
def _normalize_header(text: str) -> str:
    if text is None: return ""
    s = str(text)
    s = re.sub(r"[_\-\.\[\]\(\)\{\}:]", " ", s)
    s = s.replace("¿", "").replace("?", "").replace("¡", "").replace("!", "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s).strip().lower()

def _looks_like_timestamp(norm_name: str) -> bool:
    if not norm_name: return False
    if "marca temporal" in norm_name or "timestamp" in norm_name: return True
    tokens = norm_name.split()
    if len(tokens) <= 4 and any(kw in norm_name for kw in ["fecha", "date", "created", "creado", "submitted", "respuesta"]): return True
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

def _detect_special_columns(columns):
    date_col = None
    question_cols = []
    for col in columns:
        norm = _normalize_header(col)
        if date_col is None and _looks_like_timestamp(norm):
            date_col = col
            continue
        if _is_metadata_column(norm): continue
        question_cols.append(col)
    return date_col, question_cols

def _infer_demographic_flags(col_name: str):
    norm = _normalize_header(col_name)
    is_demo = False
    demo_type = None
    if any(k in norm for k in ["edad", "age", "rango de edad"]): is_demo = True; demo_type = "age"
    elif any(k in norm for k in ["genero", "gender", "sexo"]): is_demo = True; demo_type = "gender"
    return is_demo, demo_type


# ----------------------------------------------------------------------
# Tarea 1: DELETE (La que estaba dando KeyError)
# ----------------------------------------------------------------------
@shared_task(bind=True, name="surveys.tasks.delete_surveys_task", max_retries=2)
def delete_surveys_task(self, survey_ids, user_id):
    from surveys.models import Survey as SurveyModel
    if hasattr(user_id, "pk"): user_id = user_id.pk
    else: user_id = int(user_id)
    try:
        with transaction.atomic():
            qs = SurveyModel.objects.filter(id__in=survey_ids, author_id=user_id)
            owned_ids = list(qs.values_list("id", flat=True))
            if not owned_ids: return {"success": False, "error": "No permissions"}
            ids_tuple = tuple(owned_ids)
            placeholders = ", ".join(["%s"] * len(ids_tuple))
            with connection.cursor() as cursor:
                # Borrado optimizado
                cursor.execute(f"DELETE FROM surveys_questionresponse WHERE survey_response_id IN (SELECT id FROM surveys_surveyresponse WHERE survey_id IN ({placeholders}))", ids_tuple)
                cursor.execute(f"DELETE FROM surveys_surveyresponse WHERE survey_id IN ({placeholders})", ids_tuple)
            count, _ = qs.delete()
            # 'count' is the total number of DB objects removed (includes cascades)
            # Return also the number of surveys requested so callers can show a
            # user-friendly count (number of surveys), not the total deleted objects.
            return {"success": True, "deleted": count, "deleted_surveys": len(owned_ids)}
    except Exception as e:
        logger.error("[DELETE_SURVEYS][ERROR] %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


# ----------------------------------------------------------------------
# Tarea 2: IMPORT (La que estaba causando la importación circular)
# ----------------------------------------------------------------------
@shared_task(bind=True, name="surveys.tasks.process_survey_import", max_retries=1)
def process_survey_import(self, log_id):
    try:
        log = ImportJob.objects.select_related("user").get(id=log_id)

        if log.status in ("processing", "completed"):
            return {"success": False, "error": f"Log ya en estado {log.status}"}

        log.status = "processing"
        log.save(update_fields=["status", "updated_at"])

        csv_path = str(log.csv_file)
        if hasattr(log.csv_file, "path"): csv_path = log.csv_file.path
        user = log.user

        raw_title = log.survey_title or log.original_filename or os.path.basename(csv_path)
        raw_title = (raw_title or "").strip()
        if "." in raw_title: raw_title = raw_title.rsplit(".", 1)[0]
        title = raw_title[:255] or f"Encuesta importada {timezone.now().strftime('%Y-%m-%d %H:%M')}"

        try: df = pd.read_csv(csv_path, sep=None, engine="python", encoding="utf-8-sig")
        except:
            try: df = pd.read_csv(csv_path, sep=None, engine="python", encoding="latin-1")
            except Exception as e: raise Exception(f"Formato inválido: {e}")

        if df is None or df.empty: raise Exception("Archivo vacío o ilegible.")
        df = df.dropna(axis=1, how="all")

        all_columns = df.columns.tolist()
        date_column_name, question_columns = _detect_special_columns(all_columns)
        if not question_columns: raise Exception("No se encontraron columnas de preguntas válidas.")

        with transaction.atomic():
            survey = Survey.objects.create(title=title, description=f"Importada el {timezone.now().strftime('%d/%m/%Y')}", status="closed", author=user, is_imported=True)
            questions_to_create = []
            questions_map = {}
            for idx, col_name in enumerate(question_columns):
                series = df[col_name]; sample = series.dropna()
                col_type = "text"; sample_str = sample.astype(str)
                sample_numeric = pd.to_numeric(sample_str.str.replace(",", "."), errors="coerce")
                is_mostly_numeric = (sample_numeric.notnull().sum() > (len(sample_numeric) * 0.8) if len(sample_numeric) > 0 else False)
                unique_count = sample_str.nunique()
                if is_mostly_numeric: col_type = "scale" if (sample_numeric.max() <= 10 and sample_numeric.min() >= 0) else "number"
                elif sample_str.str.contains(",").any() or sample_str.str.contains(";").any():
                    if unique_count > 1: col_type = "multi"
                elif 0 < unique_count < 20: col_type = "single"
                else: col_type = "text"
                is_demo, demo_type = _infer_demographic_flags(col_name)
                q = Question(survey=survey, text=str(col_name)[:500], type=col_type, order=idx, is_demographic=is_demo, demographic_type=demo_type, is_analyzable=True)
                questions_to_create.append(q)
                questions_map[col_name] = {"question": q, "dtype": col_type}

            Question.objects.bulk_create(questions_to_create)
            saved_questions = list(Question.objects.filter(survey=survey).order_by("order"))
            for i, q_obj in enumerate(saved_questions):
                col_name = question_columns[i]
                questions_map[col_name]["question"] = q_obj
                dtype = questions_map[col_name]["dtype"]
                if dtype in ("single", "multi"):
                    sample = df[col_name].dropna().astype(str); unique_opts = set()
                    for val in sample:
                        if dtype == "multi": parts = re.split(r"[;,]", val); unique_opts.update([x.strip() for x in parts if x.strip()])
                        else: unique_opts.add(val.strip())
                    opts_objs = [AnswerOption(question=q_obj, text=opt[:255], order=j) for j, opt in enumerate(sorted(unique_opts))]
                    AnswerOption.objects.bulk_create(opts_objs)
                    saved_opts = {o.text: o for o in AnswerOption.objects.filter(question=q_obj)}
                    questions_map[col_name]["options"] = saved_opts

        total_rows, inserted_rows = bulk_import_responses_postgres(survey, df, questions_map, date_column=date_column_name)

        log.status = "completed"
        log.survey = survey
        log.total_rows = len(df)
        log.processed_rows = inserted_rows
        log.save()

        try:
            if os.path.exists(csv_path): os.remove(csv_path)
        except OSError: logger.warning("[IMPORT][CLEANUP] No se pudo eliminar %s", csv_path)

        return {"success": True, "survey_id": survey.id, "rows": inserted_rows}

    except Exception as exc:
        logger.error("[IMPORT][CRITICAL] %s", exc, exc_info=True)
        try:
            log = ImportJob.objects.get(id=log_id)
            log.status = "failed"
            log.error_message = str(exc)[:500]
            log.save()
        except Exception:
            logger.error("[IMPORT][CRITICAL][NO_LOG] %s", exc, exc_info=True)
        return {"success": False, "error": str(exc)}