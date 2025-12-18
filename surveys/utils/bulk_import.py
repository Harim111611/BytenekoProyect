import csv
import io
import re
import logging
from typing import Optional, Tuple, List, Any, Dict

# Importación del módulo C++ (Requerido)
import cpp_csv

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from dateutil import parser

from surveys.models import SurveyResponse, QuestionResponse, Question, AnswerOption

logger = logging.getLogger(__name__)

# =============================================================================
# Helpers de Limpieza y Detección
# =============================================================================

def _normalize_header(name: str) -> str:
    return str(name).strip().lower()

def _is_date_column(header: str) -> bool:
    """Detecta si una columna es de fecha basándose en el nombre."""
    h = _normalize_header(header)
    keywords = ['fecha', 'date', 'time', 'marca temporal', 'timestamp', 'creado', 'created']
    return any(k in h for k in keywords)

def _is_metadata_column(header: str) -> bool:
    """Ignora columnas que no son preguntas."""
    h = _normalize_header(header)
    return h in ('id', 'pk') or h.startswith('unnamed')

def parse_date_safe(value: str) -> Optional[Any]:
    """Intenta parsear una fecha desde string."""
    if not value: return None
    try:
        return parser.parse(value)
    except:
        return None

def _infer_column_type(header: str, sample_values: List[str]) -> str:
    """
    Infiere el tipo de pregunta (text, number, scale, multi, single)
    basándose en una muestra de valores de esa columna.
    """
    if not sample_values:
        return 'text'

    # Verificar si es numérico
    is_numeric = True
    is_scale = True
    has_separators = False
    
    for v in sample_values:
        if not v: continue
        if ',' in v or ';' in v:
            has_separators = True
        
        # Check numérico simple
        if not re.match(r'^-?\d+(\.\d+)?$', v.replace(',', '.')):
            is_numeric = False
            is_scale = False
        else:
            # Check escala (0-10)
            try:
                num = float(v.replace(',', '.'))
                if num < 0 or num > 10:
                    is_scale = False
            except:
                is_scale = False

    if is_scale: return 'scale'
    if is_numeric: return 'number'
    if has_separators: return 'multi'
    
    # Heurística para Single Choice: pocos valores únicos repetidos
    unique_count = len(set(sample_values))
    total_count = len(sample_values)
    if total_count > 5 and unique_count <= 10: # Ejemplo: Sí, No, Tal vez
        return 'single'

    return 'text'

def _prepare_questions_map(survey, headers: List[str], rows: List[Dict[str, str]], date_col: str) -> Dict[str, Any]:
    """
    Asegura que existan las preguntas en la BD y retorna un mapa para la importación.
    """
    questions_map = {}
    
    # Obtener preguntas existentes para no duplicar si se re-importa
    existing_questions = {q.text: q for q in survey.questions.all()}
    questions_to_create = []
    
    # Analizar columnas
    cols_analysis = []
    
    for col in headers:
        if col == date_col or _is_metadata_column(col):
            continue
            
        # Tomar una muestra de hasta 50 valores no vacíos para inferir tipo
        sample = [r[col] for r in rows[:50] if r.get(col)]
        dtype = _infer_column_type(col, sample)
        
        q_obj = existing_questions.get(col)
        if not q_obj:
            # Crear objeto en memoria para bulk_create
            q_obj = Question(
                survey=survey,
                text=col,
                type=dtype,
                order=len(existing_questions) + len(questions_to_create) + 1
            )
            questions_to_create.append(q_obj)
        
        cols_analysis.append({
            'col_name': col,
            'question': q_obj, # Puede no tener ID aún
            'dtype': dtype,
            'sample': sample
        })

    # Crear preguntas nuevas en masa
    if questions_to_create:
        Question.objects.bulk_create(questions_to_create)
        # Recargar para obtener IDs
        existing_questions = {q.text: q for q in survey.questions.all()}
        for item in cols_analysis:
            if item['question'].id is None:
                item['question'] = existing_questions.get(item['col_name'])

    # Procesar Opciones para Single/Multi
    options_to_create = []
    # Cache de opciones: {question_id: {text: option_obj}}
    options_cache = {} 

    # Precargar opciones existentes
    all_options = AnswerOption.objects.filter(question__survey=survey)
    for opt in all_options:
        if opt.question_id not in options_cache:
            options_cache[opt.question_id] = {}
        options_cache[opt.question_id][opt.text] = opt

    for item in cols_analysis:
        q = item['question']
        if item['dtype'] in ('single', 'multi'):
            if q.id not in options_cache:
                options_cache[q.id] = {}
            
            # Detectar opciones únicas en la muestra
            unique_vals = set()
            for r in rows:
                val = r.get(item['col_name'], '')
                if not val: continue
                parts = [val] if item['dtype'] == 'single' else val.replace(';', ',').split(',')
                for p in parts:
                    clean = p.strip()
                    if clean: unique_vals.add(clean)
            
            for val_text in unique_vals:
                if val_text not in options_cache[q.id]:
                    # Crear opción
                    new_opt = AnswerOption(question=q, text=val_text)
                    options_to_create.append(new_opt)
                    # Agregar al cache temporalmente (sin ID) para no duplicar en este loop
                    options_cache[q.id][val_text] = new_opt

    if options_to_create:
        AnswerOption.objects.bulk_create(options_to_create)
        # Recargar opciones para tener IDs
        all_options = AnswerOption.objects.filter(question__survey=survey)
        options_cache = {}
        for opt in all_options:
            if opt.question_id not in options_cache:
                options_cache[opt.question_id] = {}
            options_cache[opt.question_id][opt.text] = opt

    # Construir mapa final
    for item in cols_analysis:
        q = item['question']
        questions_map[item['col_name']] = {
            'question': q,
            'dtype': item['dtype'],
            'options': options_cache.get(q.id, {})
        }
        
    return questions_map

# =============================================================================
# Función Principal
# =============================================================================

def bulk_import_responses_postgres(file_path: str, survey) -> Tuple[int, int]:
    """
    Importación optimizada usando C++ para lectura en streaming y COPY para escritura.
    Optimizado para 4GB RAM y múltiples importaciones simultáneas.
    """
    import gc  # Para liberar memoria explícitamente
    
    # 1. Lectura con C++ - Usar sampling para preparación inicial
    logger.info(f"[IMPORT][MEMORY] Iniciando importación optimizada para 4GB")
    
    try:
        # Primero leer solo una muestra para analizar estructura
        sample_size = min(getattr(settings, "SURVEY_IMPORT_SAMPLE_SIZE", 5000), 5000)
        # La versión actual de cpp_csv no soporta max_rows, leemos y truncamos en Python
        sample_rows = cpp_csv.read_csv_dicts(file_path)[:sample_size]
        
        if not sample_rows:
            logger.warning("[IMPORT] CSV vacío o sin datos válidos")
            return 0, 0
            
        headers = list(sample_rows[0].keys())
        
    except Exception as e:
        logger.error(f"[IMPORT][ERROR] Error leyendo CSV con módulo C++: {e}")
        raise

    # 2. Detectar columna de fecha desde la muestra
    date_column = None
    for h in headers:
        if _is_date_column(h):
            date_column = h
            break
            
    # 3. Preparar Estructura (Preguntas y Opciones) - solo con muestra
    logger.info(f"[IMPORT][PREP] Preparando estructura con muestra de {len(sample_rows)} filas")
    questions_map = _prepare_questions_map(survey, headers, sample_rows, date_column)
    
    # Liberar memoria de la muestra
    del sample_rows
    gc.collect()
    
    # 4. Ahora leer el archivo completo en chunks usando cpp_csv
    chunk_size = getattr(settings, "SURVEY_IMPORT_CHUNK_SIZE", 2500)  # Más pequeño para 4GB
    total_rows_processed = 0
    final_rows_inserted = 0
    
    logger.info(f"[IMPORT][START] Procesando archivo completo con chunks de {chunk_size}")
    
    # Leer archivo completo de una vez (cpp_csv es eficiente)
    try:
        all_rows = cpp_csv.read_csv_dicts(file_path)
        total_rows = len(all_rows)
        logger.info(f"[IMPORT][LOADED] {total_rows} filas cargadas desde CSV")
    except Exception as e:
        logger.error(f"[IMPORT][ERROR] Error en lectura completa: {e}")
        raise
    
    # Procesar en chunks para controlar memoria (MAGIA NEGRA™)
    for chunk_idx, i in enumerate(range(0, total_rows, chunk_size)):
        chunk_rows = all_rows[i : i + chunk_size]
        chunk_size_actual = len(chunk_rows)
        
        logger.info(f"[IMPORT][CHUNK {chunk_idx}] Procesando {chunk_size_actual} filas (offset {i})")
        
        with transaction.atomic():
            # A. Crear SurveyResponses con bulk_create optimizado
            sr_objects = []
            for row in chunk_rows:
                dt = timezone.now()
                if date_column and row.get(date_column):
                    parsed = parse_date_safe(row[date_column])
                    if parsed: 
                        if timezone.is_naive(parsed):
                            parsed = timezone.make_aware(parsed)
                        dt = parsed
                
                sr_objects.append(SurveyResponse(survey=survey, created_at=dt, is_anonymous=True))
            
            # bulk_create sin retrieve de IDs cuando no es necesario
            created_srs = SurveyResponse.objects.bulk_create(sr_objects, batch_size=1000)
            
            # B. Preparar buffer para COPY
            qr_buffer = io.StringIO()
            qr_writer = csv.writer(qr_buffer, delimiter="\t", quotechar='"', quoting=csv.QUOTE_MINIMAL)
            
            batch_qr_count = 0
            
            for idx, row in enumerate(chunk_rows):
                sr_id = created_srs[idx].id
                
                for col_name, val_str in row.items():
                    # Ignorar metadatos o columnas no mapeadas
                    if col_name not in questions_map:
                        continue
                        
                    val_str = val_str.strip()
                    if not val_str:
                        continue
                        
                    q_map = questions_map[col_name]
                    q_id = q_map['question'].id
                    dtype = q_map['dtype']
                    options = q_map['options']
                    
                    # Valores por defecto para COPY (\N es NULL en postgres text format)
                    so_id = "\\N"
                    text_val = "\\N"
                    num_val = "\\N"
                    
                    # Lógica de mapeo según tipo
                    if dtype in ('single', 'multi'):
                        # Intentar separar si es multi
                        parts = [val_str] if dtype == 'single' else val_str.replace(';', ',').split(',')
                        for p in parts:
                            p_clean = p.strip()
                            if not p_clean: continue
                            
                            if p_clean in options:
                                # Opción encontrada
                                qr_writer.writerow([sr_id, q_id, options[p_clean].id, "\\N", "\\N"])
                            else:
                                # Opción abierta/otra
                                clean_txt = p_clean.replace("\n", " ").replace("\r", "")[:2000]
                                qr_writer.writerow([sr_id, q_id, "\\N", clean_txt, "\\N"])
                            batch_qr_count += 1
                        continue # Ya escribimos las filas para esta columna
                        
                    elif dtype in ('number', 'scale'):
                        # Intentar sacar número
                        try:
                            clean_num_str = re.sub(r'[^\d\.\-]', '', val_str.replace(',', '.'))
                            if clean_num_str:
                                num_val = int(float(clean_num_str))
                            else:
                                text_val = val_str.replace("\n", " ").replace("\r", "")[:2000]
                        except:
                            text_val = val_str.replace("\n", " ").replace("\r", "")[:2000]
                            
                    else: # Texto
                        text_val = val_str.replace("\n", " ").replace("\r", "")[:5000]

                    qr_writer.writerow([sr_id, q_id, so_id, text_val, num_val])
                    batch_qr_count += 1

            final_rows_inserted += batch_qr_count
            logger.info(f"[IMPORT][CHUNK {chunk_idx}] Insertadas {batch_qr_count} respuestas")
            
            # C. Ejecutar COPY con acceso al cursor nativo (MAGIA NEGRA™)
            qr_buffer.seek(0)
            table_name = QuestionResponse._meta.db_table
            sql = f"COPY {table_name} (survey_response_id, question_id, selected_option_id, text_value, numeric_value) FROM STDIN WITH (FORMAT CSV, DELIMITER '\t', QUOTE '\"', NULL '\\N')"
            
            with connection.cursor() as cursor:
                try:
                    raw_cursor = getattr(cursor, 'cursor', cursor) 

                    # Psycopg2 o Psycopg 3
                    if hasattr(raw_cursor, 'copy_expert'):
                        raw_cursor.copy_expert(sql, qr_buffer)
                    elif hasattr(raw_cursor, 'copy'):
                        with raw_cursor.copy(sql) as copy:
                            copy.write(qr_buffer.read())
                    else:
                        logger.error("[IMPORT][ERROR] Driver no soporta COPY masivo")
                        raise NotImplementedError("Driver incompatible con COPY")
                        
                except Exception as e:
                    logger.error(f"[IMPORT][ERROR] Error crítico en COPY: {e}")
                    raise
        
        # Liberar memoria después de cada chunk (MAGIA NEGRA™)
        total_rows_processed += chunk_size_actual
        del chunk_rows, sr_objects, created_srs
        gc.collect()
        
        logger.info(f"[IMPORT][PROGRESS] {total_rows_processed}/{total_rows} filas procesadas ({(total_rows_processed/total_rows)*100:.1f}%)")

    # Liberar memoria final
    del all_rows
    gc.collect()
    
    logger.info(f"[IMPORT][COMPLETE] Total: {total_rows} filas, {final_rows_inserted} respuestas insertadas")
    return total_rows, final_rows_inserted