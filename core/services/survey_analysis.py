"""Ultra-optimized survey analysis helpers."""

import logging
import re
import string
import time
import unicodedata
import math
from collections import Counter, defaultdict
import statistics

from django.core.cache import cache
from django.db import connection

from core.utils.logging_utils import log_performance
from core.utils.charts import ChartGenerator  # Importación necesaria para gráficos

logger = logging.getLogger(__name__)

CACHE_TIMEOUT_ANALYSIS = 3600  # 1 hour

STOP_WORDS = {
    'este', 'esta', 'estas', 'estos', 'para', 'pero', 'porque', 'pues', 'solo', 'sobre', 'todo', 'tantos',
    'todas', 'todos', 'tras', 'ademas', 'cada', 'como', 'cuando', 'donde', 'entonces', 'entre', 'hasta',
    'luego', 'mientras', 'mucho', 'poco', 'segun', 'siempre', 'tambien', 'tanto', 'teneis', 'tengo',
    'tenia', 'tenian', 'tenias', 'tenido', 'tenidos', 'teniendo', 'tenemos', 'tener', 'tienes',
    'que', 'con', 'los', 'las', 'una', 'uno', 'unos', 'unas', 'del', 'por', 'estoy', 'estan', 'estas',
    'usted', 'ustedes', 'ellos', 'ellas', 'ser', 'son', 'era', 'eran', 'fue', 'fueron', 'muy', 'mas', 'menos',
    'muchas', 'muchos', 'nuestro', 'nuestra', 'nuestros', 'nuestras', 'sus', 'sino', 'sin', 'sobre',
    'the', 'and', 'this', 'that', 'with', 'from', 'have', 'been', 'were', 'will', 'would', 'there', 'their',
    'which', 'about', 'more', 'some', 'than', 'into', 'your', 'just', 'them', 'they', 'very', 'much', 'many',
    'here', 'only', 'even', 'what', 'when', 'where', 'while', 'also', 'back', 'down', 'over', 'such', 'most',
    'other', 'really', 'still', 'well', 'mucho', 'algo', 'algun', 'ningun', 'ninguna', 'asi', 'aunque', 'desde',
    # Términos técnicos de logs y user agents
    'mozilla', 'chrome', 'safari', 'edge', 'firefox', 'windows', 'linux', 'android', 'iphone', 'macos',
    # Errores de datos
    'null', 'none', 'nan', 'undefined', 'empty'
}

class ContextAutomaton:
    """
    Automata para determinar el contexto y sentimiento de una pregunta/respuesta.
    Simula un análisis de lenguaje para categorizar 'bueno' o 'malo' según el dominio.
    
    ESTADOS Y SU SIGNIFICADO (para usuarios NO técnicos):
    =====================================================
    Los resultados numéricos se categorizan en 4 estados de criticidad:
    
    - EXCELENTE: Resultados óptimos. El indicador está en niveles altos/positivos.
      → Acción: Mantén la consistencia y monitorea.
    
    - BUENO: Resultados sólidos. El indicador funciona bien pero tiene margen de mejora.
      → Acción: Refuerza lo que está funcionando.
    
    - REGULAR: Resultados mediocres. Hay espacio significativo para mejorar.
      → Acción: Investiga causas raíz e implementa cambios.
    
    - CRÍTICO: Resultados pobres o problemas detectados. Requiere atención inmediata.
      → Acción: Prioriza esta área para intervención urgente.
    
    Estos estados se usan para ordenar los "top_insights" en el dashboard:
    los problemas más críticos (CRÍTICO y REGULAR) se muestran primero para
    que el usuario identifique rápidamente qué necesita atender.
    """
    CONTEXTS = {
        'TIEMPO': ['tiempo', 'demora', 'espera', 'tardanza', 'rapidez', 'velocidad', 'minutos', 'horas', 'lento', 'rapido'],
        'ATENCION': ['atencion', 'amabilidad', 'trato', 'personal', 'staff', 'empleado', 'soporte', 'ayuda'],
        'CALIDAD': ['calidad', 'limpieza', 'estado', 'funcionamiento', 'sabor', 'confort', 'comodidad'],
        'PRECIO': ['precio', 'costo', 'valor', 'pagar', 'caro', 'barato', 'economico'],
        'PROCESO': ['proceso', 'tramite', 'facilidad', 'dificultad', 'uso', 'app', 'web', 'sistema']
    }

    NEGATIVE_INDICATORS = ['mal', 'pesimo', 'lento', 'caro', 'sucio', 'dificil', 'error', 'fallo', 'problema', 'queja']
    POSITIVE_INDICATORS = ['bien', 'excelente', 'rapido', 'barato', 'limpio', 'facil', 'perfecto', 'bueno', 'gran']

    @classmethod
    def detect_context(cls, text):
        norm = normalize_text(text)
        for ctx, keywords in cls.CONTEXTS.items():
            if any(k in norm for k in keywords):
                return ctx
        return 'GENERAL'

    @classmethod
    def analyze_numeric_result(cls, context, avg, scale_cap, question_text):
        """Determina si un resultado numérico es bueno o malo según el contexto.
        
        Esta función es la clave para determinar el estado (EXCELENTE, BUENO, REGULAR, CRÍTICO).
        
        Lógica de polaridad:
        - Para la mayoría de preguntas: "Más es Mejor" (ej. Satisfacción, Rapidez)
          → Una puntuación alta = EXCELENTE
        - Para algunas áreas: "Menos es Mejor" (ej. Tiempo de espera, Costo)
          → Una puntuación baja = EXCELENTE
        
        El resultado final se normaliza a 0-10 y se categoriza según:
        - 8-10: EXCELENTE
        - 6-8: BUENO
        - 4-6: REGULAR
        - 0-4: CRÍTICO
        """
        norm_text = normalize_text(question_text)
        
        # Determinar polaridad de la métrica (¿Más es mejor o peor?)
        # Por defecto: Más es Mejor (Satisfacción)
        lower_is_better = False
        
        if context == 'TIEMPO':
            if not any(k in norm_text for k in ['satisfaccion', 'calificacion', 'rapidez', 'velocidad']):
                lower_is_better = True # "Tiempo de espera" -> Menos es mejor
        elif context == 'PRECIO':
             if 'caro' in norm_text or 'costo' in norm_text:
                 lower_is_better = True
        elif context == 'PROCESO':
             if 'dificultad' in norm_text or 'esfuerzo' in norm_text or 'errores' in norm_text:
                 lower_is_better = True

        # Normalizar a 0-10
        score = (avg / scale_cap) * 10
        
        if lower_is_better:
            # Invertir score para análisis unificado (0=Malo, 10=Bueno)
            # Si score real es 10 (muy alto tiempo), performance es 0.
            # Si score real es 0 (muy bajo tiempo), performance es 10.
            performance = 10 - score
        else:
            performance = score
            
        if performance >= 8: return 'EXCELENTE', lower_is_better
        if performance >= 6: return 'BUENO', lower_is_better
        if performance >= 4: return 'REGULAR', lower_is_better
        return 'CRITICO', lower_is_better

    @classmethod
    def generate_recommendations(cls, context, state, lower_is_better):
        """Genera recomendaciones basadas en estados del autómata."""
        recs = []
        if state in ['CRITICO', 'REGULAR']:
            if context == 'TIEMPO':
                recs.append("Realiza un estudio de tiempos y movimientos para identificar cuellos de botella.")
                recs.append("Considera aumentar el personal en horas pico para reducir la espera.")
            elif context == 'ATENCION':
                recs.append("Implementa programas de capacitación en servicio al cliente para el personal.")
                recs.append("Revisa los protocolos de atención y resolución de conflictos.")
            elif context == 'CALIDAD':
                recs.append("Audita los estándares de calidad y mantenimiento de las instalaciones/productos.")
                recs.append("Establece controles de calidad más rigurosos antes de la entrega.")
            elif context == 'PRECIO':
                recs.append("Evalúa la percepción de valor vs precio; comunica mejor los beneficios.")
                recs.append("Considera ofertas o paquetes para mejorar la competitividad.")
            elif context == 'PROCESO':
                recs.append("Simplifica los pasos necesarios para completar la acción.")
                recs.append("Mejora la usabilidad de las herramientas o interfaces.")
            else:
                recs.append("Investiga las causas raíz de la baja satisfacción en este punto.")
                recs.append("Contacta a los usuarios insatisfechos para entender sus necesidades.")
        else:
            recs.append("Mantén las buenas prácticas actuales y monitorea la consistencia.")
            recs.append("Identifica qué factores están generando éxito para replicarlos.")
            
        return recs

# --- DICCIONARIOS DE SENTIMIENTO ---
POSITIVE_WORDS = {
    'bien', 'bueno', 'buena', 'excelente', 'genial', 'mejor', 'gran', 'perfecto', 
    'correcto', 'fácil', 'facil', 'rápido', 'rapido', 'útil', 'util', 'feliz', 
    'contento', 'satisfecho', 'gracias', 'eficaz', 'eficiente', 'amable', 
    'profesional', 'encanta', 'gusta', 'increíble', 'maravilloso', 'agradable', 
    'limpio', 'claridad', 'ayuda', 'solución', 'calidad', 'si', 'yes', 'ok'
}

NEGATIVE_WORDS = {
    'mal', 'malo', 'mala', 'pésimo', 'pesimo', 'peor', 'horrible', 'lento', 
    'difícil', 'dificil', 'complicado', 'error', 'fallo', 'problema', 'deficiente', 
    'inútil', 'inutil', 'caro', 'costoso', 'tarde', 'demora', 'espera', 'nunca', 
    'jamás', 'triste', 'enojado', 'sucio', 'desordenado', 'grosero', 'lenta', 
    'ruido', 'caos', 'falla', 'nadie', 'falta', 'no', 'queja', 'bugs', 'lenta'
}

AGE_KEYWORDS = [
    'edad', 'age', 'anos', 'years', 'cuantos anos', 'how old', 
    'rango edad', 'age range', 'grupo edad', 'age group', 'fecha nacimiento',
    'years old', 'years-old', 'cuantos years'
]

def normalize_text(text):
    """Normalización agresiva para análisis semántico."""
    if not text: return ''
    text_str = str(text)
    text_str = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text_str)
    text_str = re.sub(r'[_\-\.\[\]\(\)\{\}:]', ' ', text_str)
    text_str = text_str.replace('¿', '').replace('?', '').replace('¡', '').replace('!', '')
    normalized = unicodedata.normalize('NFKD', text_str).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', normalized).strip().lower()


class SurveyAnalysisService:
    """Ultra-optimized survey analysis service using raw SQL."""

    @staticmethod
    @log_performance(threshold_ms=2000)
    def get_analysis_data(survey, responses_queryset, include_charts=True, cache_key=None, use_base_filter=True):
        """Return enriched analysis for a survey using raw SQL and lightweight post-processing."""

        # --- 0. INICIALIZACIÓN ---
        nps_data = {'score': None, 'promoters': 0, 'passives': 0, 'detractors': 0, 'chart_image': None}
        satisfaction_avg = 0
        heatmap_image = None
        heatmap_image_dark = None
        skipped_questions = []
        filtered_questions = []
        cardinality_info = {}
        analysis_data = []

        questions = list(survey.questions.prefetch_related('options').order_by('order'))
        questions_map = {q.id: q for q in questions}

        # --- 1. DEFINICIÓN DE PALABRAS CLAVE ---
        date_keywords = ['fecha', 'date', 'created', 'creado', 'timestamp', 'time']
        
        identifier_keywords = [
            'nombre', 'name', 'apellido', 'lastname', 'surname', 'fullname', 'full name',
            'correo', 'email', 'mail', 'e-mail', 'direccion', 'address',
            'telefono', 'tel', 'phone', 'celular', 'mobile', 'movil', 'whatsapp',
            'id', 'identificacion', 'identification', 'documento', 'dni', 'curp', 'rfc', 'cedula', 
            'passport', 'pasaporte', 'ssn', 'matricula', 'legajo',
            'ip', 'ip_address', 'ip address', 'direccion ip', 'mac address',
            'user_agent', 'user agent', 'browser', 'navegador', 'dispositivo', 'device',
            'uuid', 'guid', 'token', 'session', 'cookie', 
            'user', 'usuario', 'login', 'username', 'user name',
            'reserva', 'booking', 'ticket', 'folio', 'transaction', 'transaccion',
            'latitud', 'latitude', 'longitud', 'longitude', 'geo'
        ]

        metadata_keywords = [
            'survey', 'encuesta', 'title', 'titulo', 'status', 'estado', 
            'network', 'red', 'referer', 'source', 'origen', 'channel', 'canal',
            'campaign', 'campana', 'medium', 'medio',
            'submit', 'enviado', 'completed', 'completado', 'time taken', 'tiempo tomado',
            'language', 'idioma'
        ]

        demographic_keywords = [
            'genero', 'gender', 'sexo', 'sex', 
            'pais', 'country', 'ciudad', 'city', 'region', 'provincia',
            'educacion', 'puesto', 'cargo', 'role', 'departamento', 'area', 'sucursal',
            'industria', 'sector'
        ]

        comment_force_keywords = [
            'comentario', 'sugerencia', 'opinion', 'feedback', 'razon', 'motivo', 
            'por que', 'porque', 'observacion', 'detalle', 'explica'
        ]

        negative_metrics_keywords = ['tiempo', 'espera', 'demora', 'tardanza', 'errores', 'fallos', 'quejas', 'costo']
        demographic_numeric_keywords = ['antiguedad', 'hijos', 'personas', 'veces', 'cantidad', 'ingresos', 'salario']
        demographic_code_keywords = ['codigo', 'code', 'zip', 'postal', 'id', 'area', 'zona', 'sucursal']

        def contains_keyword(normalized_text, keyword):
            keyword = keyword.lower()
            if ' ' in keyword: return keyword in normalized_text
            return re.search(r'\b' + re.escape(keyword) + r'\b', normalized_text) is not None

        # --- 2. PRECÁLCULO DE CARDINALIDAD ---
        for question in questions:
            qid = question.id
            if question.type in {'text', 'single'}:
                with connection.cursor() as cursor:
                    if question.type == 'text':
                        cursor.execute("SELECT COUNT(text_value), COUNT(DISTINCT text_value), AVG(LENGTH(text_value)) FROM surveys_questionresponse WHERE question_id = %s AND text_value <> ''", [qid])
                        row = cursor.fetchone()
                    else:
                        cursor.execute("SELECT COUNT(*), COUNT(DISTINCT COALESCE(ao.text, qr.text_value)), AVG(LENGTH(COALESCE(ao.text, qr.text_value))) FROM surveys_questionresponse qr LEFT JOIN surveys_answeroption ao ON qr.selected_option_id = ao.id WHERE qr.question_id = %s", [qid])
                        row = cursor.fetchone()
                    
                    n = row[0] or 0
                    unique = row[1] or 0
                    avg_len = row[2] or 0
                    ratio = (unique / n) if n > 0 else 0
                    
                    cardinality_info[qid] = {'n': n, 'unique': unique, 'ratio': ratio, 'avg_len': avg_len}

        # --- 3. CLASIFICACIÓN Y FILTRADO ---
        for question in questions:
            normalized_text = normalize_text(question.text or '')
            skip_reason = None
            
            if any(contains_keyword(normalized_text, kw) for kw in date_keywords):
                skip_reason = 'Campo temporal/fecha'
            elif any(contains_keyword(normalized_text, kw) for kw in identifier_keywords):
                is_comment_by_name = any(contains_keyword(normalized_text, kw) for kw in comment_force_keywords)
                if not is_comment_by_name and question.type in {'text', 'number'}: 
                    skip_reason = 'Dato personal / Usuario'
            elif any(contains_keyword(normalized_text, kw) for kw in metadata_keywords):
                skip_reason = 'Metadato de encuesta'
            
            # --- Detección de Edad ---
            is_age = False
            if question.type in {'number', 'scale', 'single', 'text'}:
                if any(contains_keyword(normalized_text, kw) for kw in AGE_KEYWORDS): is_age = True
            setattr(question, 'is_age_demographic', is_age)

            is_demo = False
            is_forced_comment = any(contains_keyword(normalized_text, kw) for kw in comment_force_keywords)
            
            if not is_age and not is_forced_comment and question.type in {'single', 'text', 'multi'}:
                 if any(contains_keyword(normalized_text, kw) for kw in demographic_keywords): is_demo = True
            setattr(question, 'is_general_demographic', is_demo)

            intent = 'satisfaction'
            if question.type in {'number', 'scale'} and not is_age:
                if any(k in normalized_text for k in demographic_code_keywords): intent = 'demographic_categorical_numeric'
                elif any(k in normalized_text for k in demographic_numeric_keywords): intent = 'demographic_numeric'
                elif any(k in normalized_text for k in negative_metrics_keywords): intent = 'negative_metric'
            setattr(question, 'numeric_intent', intent)

            # Heurística Anti-ID vs Comentario
            if not skip_reason and question.type in {'text', 'single'} and not is_demo:
                info = cardinality_info.get(question.id, {})
                n = info.get('n', 0)
                ratio = info.get('ratio', 0)
                avg_len = info.get('avg_len', 0)
                
                if n > 50 and ratio > 0.9:
                    if avg_len < 15 and not is_forced_comment:
                        skip_reason = 'Alta cardinalidad (posible ID)'
            
            # Fuerza análisis de texto si es Single pero parece comentario
            if not skip_reason and question.type == 'single':
                info = cardinality_info.get(question.id, {})
                unique = info.get('unique', 0)
                avg_len = info.get('avg_len', 0)
                
                if (unique > 20 or avg_len > 30 or is_forced_comment) and not is_demo and not is_age:
                    setattr(question, 'force_text_analysis', True)

            if skip_reason:
                skipped_questions.append({'id': question.id, 'text': question.text, 'reason': skip_reason})
                continue
            filtered_questions.append(question)

        if not filtered_questions:
            return _build_empty_response(filtered_questions, skipped_questions, nps_data)

        # --- 3. GENERACIÓN DE FILTROS SQL ---
        base_where_sql = ""
        base_params = []
        if use_base_filter:
            subset_query = responses_queryset.values('id').query
            compiler = subset_query.get_compiler(using=responses_queryset.db)
            sql, params = compiler.as_sql()
            base_where_sql = f" AND survey_response_id IN ({sql})"
            base_params = list(params)
            response_count = responses_queryset.count()
        else:
            response_ids = list(responses_queryset.values_list('id', flat=True)[:50000])
            if response_ids:
                placeholders = ','.join(['%s'] * len(response_ids))
                base_where_sql = f" AND survey_response_id IN ({placeholders})"
                base_params = response_ids
            response_count = len(response_ids)

        if response_count == 0:
            return _build_empty_response(filtered_questions, skipped_questions, nps_data)

        # --- 4. EJECUCIÓN DE CONSULTAS ---
        numeric_question_ids = [q.id for q in filtered_questions if q.type in {'scale', 'number'}]
        forced_text_ids = [q.id for q in filtered_questions if getattr(q, 'force_text_analysis', False)]
        
        choice_question_ids = [
            q.id for q in filtered_questions 
            if (q.type == 'single' or getattr(q, 'is_age_demographic', False) or getattr(q, 'is_general_demographic', False) or getattr(q, 'numeric_intent', '') == 'demographic_categorical_numeric')
            and q.id not in forced_text_ids
        ]
        
        text_question_ids = [q.id for q in filtered_questions if q.type == 'text' or q.id in forced_text_ids]

        numeric_stats = {}
        numeric_distributions = defaultdict(list)
        choice_distributions = defaultdict(list)
        text_counts = {}
        text_samples = defaultdict(list)
        text_responses_all = defaultdict(list)

        with connection.cursor() as cursor:
            # 4.1 Numéricos
            valid_numeric_ids = [qid for qid in numeric_question_ids if qid not in choice_question_ids]
            if valid_numeric_ids:
                ids = ','.join(map(str, valid_numeric_ids))
                where = f"question_id IN ({ids}) AND numeric_value IS NOT NULL {base_where_sql}"
                
                cursor.execute(f"SELECT question_id, COUNT(*), AVG(numeric_value), MAX(numeric_value), MIN(numeric_value) FROM surveys_questionresponse WHERE {where} GROUP BY question_id", base_params)
                for row in cursor.fetchall():
                    numeric_stats[row[0]] = {'count': row[1], 'avg': float(row[2]), 'max': float(row[3]), 'min': float(row[4])}
                
                cursor.execute(f"SELECT question_id, numeric_value, COUNT(*) FROM surveys_questionresponse WHERE {where} GROUP BY question_id, numeric_value", base_params)
                for row in cursor.fetchall():
                    numeric_distributions[row[0]].append({'value': float(row[1]), 'count': row[2]})

            # 4.2 Opciones / Categóricos
            if choice_question_ids:
                ids = ','.join(map(str, choice_question_ids))
                cursor.execute(f"""
                    SELECT qr.question_id, ao.text, COUNT(*) 
                    FROM surveys_questionresponse qr 
                    JOIN surveys_answeroption ao ON qr.selected_option_id = ao.id 
                    WHERE qr.question_id IN ({ids}) {base_where_sql.replace('survey_response_id', 'qr.survey_response_id')}
                    GROUP BY qr.question_id, ao.text
                """, base_params)
                for row in cursor.fetchall():
                    choice_distributions[row[0]].append({'option': row[1], 'count': row[2]})

                # Numérico como categoría
                cursor.execute(f"""
                    SELECT question_id, numeric_value, COUNT(*) 
                    FROM surveys_questionresponse 
                    WHERE question_id IN ({ids}) AND numeric_value IS NOT NULL {base_where_sql}
                    GROUP BY question_id, numeric_value
                """, base_params)
                for row in cursor.fetchall():
                    choice_distributions[row[0]].append({'option': str(int(row[1])), 'count': row[2]})

                # Texto Demográfico
                text_demo_ids = [
                    q.id for q in filtered_questions 
                    if (getattr(q, 'is_general_demographic', False) or getattr(q, 'is_age_demographic', False)) 
                    and q.type == 'text'
                ]
                if text_demo_ids:
                    ids_txt = ','.join(map(str, text_demo_ids))
                    cursor.execute(f"""
                        SELECT question_id, text_value, COUNT(*) 
                        FROM surveys_questionresponse 
                        WHERE question_id IN ({ids_txt}) AND text_value <> '' {base_where_sql}
                        GROUP BY question_id, text_value
                    """, base_params)
                    for row in cursor.fetchall():
                        choice_distributions[row[0]].append({'option': row[1], 'count': row[2]})

            # 4.3 Texto Libre
            if text_question_ids:
                ids = ','.join(map(str, text_question_ids))
                where = f"question_id IN ({ids}) AND text_value <> '' {base_where_sql}"
                cursor.execute(f"SELECT question_id, text_value FROM surveys_questionresponse WHERE {where}", base_params)
                for row in cursor.fetchall():
                    is_demo = getattr(questions_map.get(row[0]), 'is_general_demographic', False)
                    is_age = getattr(questions_map.get(row[0]), 'is_age_demographic', False)
                    if not is_demo and not is_age:
                        text_responses_all[row[0]].append(row[1])
                
                # Forzados
                forced_ids = [str(qid) for qid in forced_text_ids]
                if forced_ids:
                    ids_forced = ','.join(forced_ids)
                    cursor.execute(f"""
                        SELECT qr.question_id, ao.text 
                        FROM surveys_questionresponse qr 
                        JOIN surveys_answeroption ao ON qr.selected_option_id = ao.id 
                        WHERE qr.question_id IN ({ids_forced}) {base_where_sql.replace('survey_response_id', 'qr.survey_response_id')}
                    """, base_params)
                    for row in cursor.fetchall():
                        text_responses_all[row[0]].append(row[1])
                
                for qid in text_question_ids:
                    responses = text_responses_all.get(qid, [])
                    text_counts[qid] = len(responses)
                    text_samples[qid] = responses[:5]

        # --- 5. CÁLCULO DE INSIGHTS ---
        
        scale_qs = [q for q in filtered_questions if q.type == 'scale']
        if scale_qs:
            vals = [numeric_stats[q.id]['avg'] for q in scale_qs if q.id in numeric_stats]
            if vals: satisfaction_avg = sum(vals) / len(vals)
            
            nps_q = next((q for q in scale_qs if 'recomenda' in normalize_text(q.text)), None)
            if nps_q and nps_q.id in numeric_distributions:
                dist = numeric_distributions[nps_q.id]
                promoters = sum(d['count'] for d in dist if d['value'] >= 9)
                detractors = sum(d['count'] for d in dist if d['value'] <= 6)
                total = sum(d['count'] for d in dist)
                if total > 0:
                    nps_data['score'] = round(((promoters - detractors) / total) * 100, 1)
                    nps_data['promoters'] = round((promoters/total)*100, 1)
                    nps_data['detractors'] = round((detractors/total)*100, 1)
                    nps_data['passives'] = 100 - nps_data['promoters'] - nps_data['detractors']
                    if include_charts:
                         nps_data['chart_image'] = ChartGenerator.generate_nps_chart(nps_data['promoters'], nps_data['passives'], nps_data['detractors'])

        for idx, question in enumerate(filtered_questions, 1):
            item = _create_empty_question_item(question, idx)
            qid = question.id
            
            # --- CASO ESPECIAL: TEXTO (Forzado o Nativo) ---
            is_forced_text = getattr(question, 'force_text_analysis', False)
            if (question.type == 'text' or is_forced_text) and not getattr(question, 'is_age_demographic', False):
                item['type'] = 'text'
                item['tipo_display'] = 'Respuestas de Texto'
                count = text_counts.get(qid, 0)
                item['total_respuestas'] = count
                item['samples_texto'] = text_samples.get(qid, [])
                
                if count > 0:
                    texts = text_responses_all.get(qid, [])
                    all_text = ' '.join([str(t).lower() for t in texts])
                    clean = re.sub(r'[^\w\s]', ' ', all_text)
                    words = [w for w in clean.split() if len(w) > 3 and w not in STOP_WORDS]
                    
                    intro_templates = [
                        "Analizamos <strong>{count} comentarios</strong>.",
                        "Se registraron <strong>{count} opiniones</strong>.",
                        "Total de respuestas textuales: <strong>{count}</strong>.",
                    ]
                    tpl_idx = qid % len(intro_templates)
                    insight_parts = [intro_templates[tpl_idx].format(count=count)]
                    
                    if words:
                        common = Counter(words).most_common(3)
                        top_words = ", ".join([f"'{w[0]}'" for w in common])
                        keyword_templates = [
                            "Palabras clave: <strong>{kw}</strong>. Temas principales identificados.",
                            "Términos frecuentes: <strong>{kw}</strong>. Indican focos de conversación.",
                            "Más repetidos: <strong>{kw}</strong>. Revelan prioridades de la audiencia.",
                        ]
                        kw_idx = qid % len(keyword_templates)
                        insight_parts.append(keyword_templates[kw_idx].format(kw=top_words))
                        
                        pos_count = sum(1 for w in words if w in POSITIVE_WORDS)
                        neg_count = sum(1 for w in words if w in NEGATIVE_WORDS)
                        total_sent = pos_count + neg_count
                        
                        if total_sent > 0:
                            score = (pos_count - neg_count) / total_sent
                            if score > 0.2: sentiment, icon = "Positivo", "😊"
                            elif score < -0.2: sentiment, icon = "Negativo", "😟"
                            else: sentiment, icon = "Neutral", "😐"
                            sent_templates = [
                                "<br>{icon} <strong>Sentimiento: {sent}</strong>. Refleja tono general.",
                                "<br>{icon} <strong>{sent}</strong>. Predomina este matiz emocional.",
                                "<br>{icon} <strong>Análisis: {sent}</strong>. Contexto afectivo detectado.",
                            ]
                            sent_idx = qid % len(sent_templates)
                            insight_parts.append(sent_templates[sent_idx].format(icon=icon, sent=sentiment))
                    
                    item['insight'] = " ".join(insight_parts)
                    item['recommendations'] = ["Analiza los temas recurrentes para detectar problemas ocultos.", "Categoriza los comentarios por sentimiento para priorizar acciones."]
                else:
                    item['insight'] = "Aún no hemos recibido respuestas de texto para esta pregunta."
                analysis_data.append(item)
                continue

            # --- 1. DEMOGRAFÍA (CATEGÓRICA/EDAD) ---
            is_cat_num = getattr(question, 'numeric_intent', '') == 'demographic_categorical_numeric'
            is_demo = getattr(question, 'is_general_demographic', False)
            is_age = getattr(question, 'is_age_demographic', False)

            if is_cat_num or is_demo or is_age:
                item['tipo_display'] = 'Perfil Demográfico'
                if is_age: item['tipo_display'] += ' (Edad)'
                
                if is_age and qid in numeric_distributions:
                    dist = numeric_distributions[qid]
                    raw_age = {int(d['value']): d['count'] for d in dist}
                    choice_distributions[qid] = [{'option': str(k), 'count': v} for k, v in sorted(raw_age.items())]

                if qid in choice_distributions:
                    raw_dist = choice_distributions[qid]
                    grouped = defaultdict(int)
                    for d in raw_dist: grouped[d['option']] += d['count']
                    sorted_dist = sorted([{'option': k, 'count': v} for k, v in grouped.items()], key=lambda x: x['count'], reverse=True)
                    
                    item['total_respuestas'] = sum(d['count'] for d in sorted_dist)
                    top_15 = sorted_dist[:15]
                    item['chart_labels'] = [d['option'] for d in top_15]
                    item['chart_data'] = [d['count'] for d in top_15]
                    
                    if sorted_dist:
                        top = sorted_dist[0]
                        pct = round((top['count'] / item['total_respuestas']) * 100, 1)
                        # Variedad determinista por qid
                        demo_templates = [
                            "📊 <strong>Segmento dominante:</strong> {pct}% pertenece a <strong>{opt}</strong>. Este dato clave ayuda a perfilar la audiencia.",
                            "📊 <strong>Perfil principal:</strong> La categoría <strong>{opt}</strong> representa {pct}% de respuestas. Útil para estrategias segmentadas.",
                            "📊 <strong>Composición:</strong> <strong>{opt}</strong> agrupa {pct}% del total. Identifica el núcleo demográfico para acciones dirigidas.",
                        ]
                        tpl_idx = qid % len(demo_templates)
                        item['insight'] = demo_templates[tpl_idx].format(opt=top['option'], pct=pct)
                        item['recommendations'] = ["Personaliza comunicación según segmento dominante.", "Adapta la oferta de valor a las características del grupo mayoritario."]
                        
                        # Generar gráfico para PDF/PPTX
                        # Generar gráfico para PDF/PPTX
                        if include_charts:
                            if len(sorted_dist) <= 5:
                                item['chart_image'] = ChartGenerator.generate_pie_chart(item['chart_labels'], item['chart_data'], "Distribución (Top 5)")
                                item['chart_type'] = 'donut'
                            else:
                                item['chart_image'] = ChartGenerator.generate_horizontal_bar_chart(item['chart_labels'][:10], item['chart_data'][:10], "Top 10 Categorías")
                    else:
                        item['insight'] = "No tenemos suficientes datos demográficos para mostrar un patrón claro."
                analysis_data.append(item)
                continue

            # --- 2. NUMÉRICO PURO ---
            if qid in numeric_stats:
                stats = numeric_stats[qid]
                avg = stats['avg']
                scale_cap = 10 if stats['max'] > 5 else 5
                item['avg'] = avg
                item['scale_cap'] = scale_cap
                item['total_respuestas'] = stats['count']
                
                if qid in numeric_distributions:
                    dist = sorted(numeric_distributions[qid], key=lambda x: x['value'])
                    item['chart_labels'] = [str(int(d['value'])) for d in dist]
                    item['chart_data'] = [d['count'] for d in dist]
                    
                    if include_charts:
                        item['chart_image'] = ChartGenerator.generate_vertical_bar_chart(item['chart_labels'], item['chart_data'], "Distribución de Respuestas")

                # --- NUEVA LÓGICA CON AUTÓMATA DE CONTEXTO ---
                # 1. Detectar contexto
                context = ContextAutomaton.detect_context(question.text)
                
                # 2. Analizar resultado (Estado y Polaridad)
                state, lower_is_better = ContextAutomaton.analyze_numeric_result(context, avg, scale_cap, question.text)
                
                # Guardar para orden de insights
                item['state'] = state
                item['context'] = context
                
                # 3. Generar Recomendaciones
                recs = ContextAutomaton.generate_recommendations(context, state, lower_is_better)
                item['recommendations'] = recs
                
                # 4. Construir Insight y Display (texto más rico y extenso)
                item['tipo_display'] = f"Métrica: {context.title()}"
                
                # Iconos y Mood
                if state == 'EXCELENTE': icon, mood = "🌟", "Excelente"
                elif state == 'BUENO': icon, mood = "✅", "Bueno"
                elif state == 'REGULAR': icon, mood = "⚠️", "Regular"
                else: icon, mood = "🛑", "Crítico"
                
                # Determinar artículo según género del contexto
                ctx_lower = context.lower()
                article = "la" if context in ['ATENCION', 'CALIDAD'] else "el"
                
                # Templates dinámicos según si "Menos es Mejor" (Tiempo/Precio) o "Más es Mejor" (Calidad/Satisfacción)
                if lower_is_better:
                    # Contexto negativo (ej. Tiempo de espera): Bajo es bueno
                    insight_templates = [
                        "{icon} <strong>{mood}</strong>: Promedio {avg:.1f}. {ctx_title} bajo control. Mantén la eficiencia.",
                        "{icon} <strong>Desempeño {mood}</strong> ({avg:.1f}). {art} {ctx} está en niveles óptimos.",
                        "{icon} <strong>Estado: {mood}</strong>. Valor {avg:.1f}. Gestión de {ctx} efectiva."
                    ] if state in ['EXCELENTE', 'BUENO'] else [
                        "{icon} <strong>{mood}</strong>: Promedio {avg:.1f}. {art} {ctx} es alto. Requiere atención inmediata.",
                        "{icon} <strong>Alerta {mood}</strong> ({avg:.1f}). Optimiza procesos para reducir este valor.",
                        "{icon} <strong>Estado: {mood}</strong>. Valor {avg:.1f}. Detectamos fricción en {ctx}."
                    ]
                else:
                    # Contexto positivo (ej. Satisfacción): Alto es bueno
                    insight_templates = [
                        "{icon} <strong>{mood}</strong>: {avg:.1f}/{cap}. Alta percepción de {ctx}. ¡Sigue así!",
                        "{icon} <strong>Nivel {mood}</strong> ({avg:.1f}). Los usuarios valoran positivamente {art} {ctx}.",
                        "{icon} <strong>Valoración: {mood}</strong>. Puntuación {avg:.1f}. Fortaleza clave en {ctx}."
                    ] if state in ['EXCELENTE', 'BUENO'] else [
                        "{icon} <strong>{mood}</strong>: {avg:.1f}/{cap}. Baja percepción de {ctx}. Prioriza mejoras.",
                        "{icon} <strong>Nivel {mood}</strong> ({avg:.1f}). {art_title} {ctx} requiere intervención estratégica.",
                        "{icon} <strong>Valoración: {mood}</strong>. Puntuación {avg:.1f}. Punto de dolor detectado en {ctx}."
                    ]
                
                tpl_idx = qid % len(insight_templates)
                base_insight = insight_templates[tpl_idx].format(
                    icon=icon, 
                    mood=mood, 
                    avg=avg, 
                    cap=scale_cap, 
                    ctx=ctx_lower,
                    ctx_title=context.title(),
                    art=article,
                    art_title=article.title()
                )

                # Añadir análisis complementario según distribución y conteo para alargar el texto de forma útil
                extras = []
                try:
                    if qid in numeric_distributions:
                        dist_sorted = sorted(numeric_distributions[qid], key=lambda x: x['value'])
                        counts_only = [d['count'] for d in dist_sorted]
                        total = sum(counts_only) or 1
                        high_tail = sum(c for v, c in [(d['value'], d['count']) for d in dist_sorted] if v >= (scale_cap*0.7))
                        low_tail = sum(c for v, c in [(d['value'], d['count']) for d in dist_sorted] if v <= (scale_cap*0.3))
                        pct_high = round((high_tail/total)*100, 1)
                        pct_low = round((low_tail/total)*100, 1)
                        extras.append(f"Distribución: {pct_high}% en valores altos y {pct_low}% en valores bajos, indicando {'polarización' if pct_high>35 and pct_low>20 else 'dispersión moderada'}. ")
                    # Comentario según estado del autómata
                    if state in ['CRITICO','REGULAR']:
                        extras.append(f"Se observan señales de fricción en {article} {ctx_lower}. Prioriza acciones tácticas inmediatas mientras defines mejoras estructurales.")
                    else:
                        extras.append(f"El indicador de {article} {ctx_lower} muestra solidez. Mantén vigilancia periódica para sostener el desempeño.")
                    # Añadir una nota de benchmarking ligera sin repetir
                    extras.append("Comparar estos resultados por segmento (edad, sucursal, canal) puede revelar variaciones relevantes para focalizar esfuerzos.")
                except Exception:
                    pass

                item['insight'] = base_insight + " " + " ".join(extras)
                
                analysis_data.append(item)
                continue

            # --- 4. SELECCIÓN SIMPLE (No demo) ---
            if qid in choice_distributions:
                item['tipo_display'] = 'Selección'
                dist = choice_distributions[qid][:10]
                item['chart_labels'] = [d['option'] for d in dist]
                item['chart_data'] = [d['count'] for d in dist]
                if dist:
                    top = dist[0]
                    total = sum(d['count'] for d in dist)
                    item['total_respuestas'] = total
                    pct = round((top['count']/total)*100, 1) if total else 0
                    # Insight con variedad de redacción según fuerza de preferencia
                    strong = pct >= 30
                    moderate = 15 <= pct < 30
                    templates_strong = [
                        "<strong>{opt}</strong> lidera con <strong>{pct}%</strong>. Predomina; refuerza disponibilidad y comunicación.",
                        "Opción ganadora: <strong>{opt}</strong> ({pct}%). Mantén ventaja con consistencia en calidad y acceso.",
                        "<strong>{opt}</strong> concentra <strong>{pct}%</strong>. Refuerza esta preferencia con propuestas dirigidas.",
                    ]
                    templates_moderate = [
                        "<strong>{opt}</strong> encabeza con <strong>{pct}%</strong>. Clara pero competitiva; segmenta mensajes por perfil.",
                        "Categoría líder: <strong>{opt}</strong> ({pct}%). Optimiza propuesta y diferénciate de alternativas cercanas.",
                        "<strong>{opt}</strong> acumula <strong>{pct}%</strong>. Preferencia moderada; monitorea cambios y ajusta estrategia.",
                    ]
                    templates_weak = [
                        "<strong>{opt}</strong> lidera con <strong>{pct}%</strong>. Preferencias distribuidas; explora microsegmentos.",
                        "<strong>{opt}</strong> apenas supera al resto ({pct}%). Prueba mejoras incrementales y ofertas dirigidas.",
                        "Elección: <strong>{opt}</strong> ({pct}%). Contexto fragmentado; considera personalización por nicho.",
                    ]
                    base = (templates_strong if strong else templates_moderate if moderate else templates_weak)
                    tpl_idx = qid % len(base)
                    lead = base[tpl_idx].format(opt=dist[0]['option'], pct=pct)
                    # Texto complementario para extender análisis sin repetición
                    spread = max(item['chart_data']) - min(item['chart_data']) if item['chart_data'] else 0
                    variety_note = "Preferencias relativamente equilibradas, sugiere ofertas moduladas por perfil." if pct < 30 else "Dominancia clara; cuida la saturación y disponibilidad." 
                    tail = "Revisar categorías con menor participación puede revelar oportunidades. "
                    tail += variety_note
                    # Añadir una observación de tendencia si existen 10 opciones
                    if len(dist) >= 5:
                        tail += f" Observación: la brecha entre líder y rezagado es de {spread} respuestas, útil para planificar promociones."
                    item['insight'] = f"{lead} {tail}"
                    
                    if pct < 20:
                        item['recommendations'] = ["Segmenta ofertas por perfil; preferencias muy distribuidas.", "Investiga por qué no hay un líder claro."]
                    elif pct > 40:
                        item['recommendations'] = ["Refuerza disponibilidad de la opción líder.", "Asegura el stock o capacidad para la opción más demandada."]
                    else:
                        item['recommendations'] = ["Monitorea la tendencia de las opciones secundarias.", "Considera promociones para balancear la demanda."]
                    
                    if include_charts:
                         if len(item['chart_labels']) <= 5:
                             item['chart_image'] = ChartGenerator.generate_pie_chart(item['chart_labels'], item['chart_data'], "Preferencias (Top 5)")
                             item['chart_type'] = 'donut'
                         else:
                             item['chart_image'] = ChartGenerator.generate_horizontal_bar_chart(item['chart_labels'], item['chart_data'], "Ranking de Opciones")

                analysis_data.append(item)

        # Heatmaps
        try:
            from core.services.analysis_service import DataFrameBuilder
            df = DataFrameBuilder.build_responses_dataframe(survey, responses_queryset)
            if not df.empty:
                heatmap_image = ChartGenerator.generate_heatmap(df, dark_mode=False)
                heatmap_image_dark = ChartGenerator.generate_heatmap(df, dark_mode=True)
        except Exception: pass

        # --- Resumen de calidad de datos (completitud de preguntas) ---
        # IMPORTANTE PARA USUARIOS NO TÉCNICOS:
        # "Calidad de datos" / "Completitud de respuestas" mide qué porcentaje de preguntas
        # fueron respondidas por los encuestados. NO mide si las respondieron bien o mal.
        # 
        # Por ejemplo:
        # - Si tenemos 10 preguntas y alguien responde 8, su completitud es 80%.
        # - Si el promedio de todas las respuestas es 90%, significa que en promedio
        #   los encuestados completaron el 90% del formulario.
        # 
        # Utilidad: Si ves que una pregunta tiene baja completitud (ej. 40%), puede
        # indicar que es confusa, no relevante, o técnicamente problemática.
        # 
        data_quality = None
        try:
            total_responses = response_count  # ya calculado más arriba
            questions_quality = []

            if total_responses > 0:
                for item in analysis_data:
                    q_total = item.get('total_respuestas') or 0
                    missing = max(total_responses - q_total, 0)
                    # completeness_pct: porcentaje de respuestas que sí contestaron esta pregunta
                    completeness_pct = round((q_total / total_responses) * 100, 1) if total_responses else 0.0

                    questions_quality.append({
                        'id': item.get('id'),
                        'text': item.get('text'),
                        'type': item.get('type'),
                        'answered': q_total,
                        'missing': missing,
                        'completeness_pct': completeness_pct,
                    })

                if questions_quality:
                    # avg_completeness_pct: promedio de completitud de todas las preguntas
                    # (cuántas preguntas, en promedio, fueron contestadas)
                    avg_completeness = sum(q['completeness_pct'] for q in questions_quality) / len(questions_quality)
                else:
                    avg_completeness = 0.0

                top_missing = sorted(questions_quality, key=lambda q: q['completeness_pct'])[:5]

                data_quality = {
                    'total_responses': total_responses,
                    'questions_analyzed': len(questions_quality),
                    'avg_completeness_pct': round(avg_completeness, 1),
                    'questions_with_most_missing': top_missing,
                    'ignored_questions': [
                        {'id': q.id, 'text': q.text}
                        for q in skipped_questions
                    ],
                }
        except Exception as e:
            logger.warning("Error computing data_quality: %s", e, exc_info=True)
            data_quality = None

        final_data = {
            'analysis_data': analysis_data,
            'nps_data': nps_data,
            'heatmap_image': heatmap_image,
            'heatmap_image_dark': heatmap_image_dark,
            'kpi_prom_satisfaccion': satisfaction_avg,
            'ignored_questions': skipped_questions,
            'data_quality': data_quality,
        }
        
        if cache_key:
            cache.set(cache_key, final_data, CACHE_TIMEOUT_ANALYSIS)
            
        return final_data

def _build_empty_response(filtered, skipped, nps_data):
    return {
        'analysis_data': [_create_empty_question_item(q, idx) for idx, q in enumerate(filtered, 1)],
        'nps_data': nps_data,
        'heatmap_image': None,
        'kpi_prom_satisfaccion': 0,
        'ignored_questions': skipped,
        'data_quality': None,
    }

def _create_empty_question_item(question, order):
    return {
        'id': question.id,
        'order': order,
        'text': question.text,
        'type': question.type,
        'tipo_display': question.get_type_display(),
        'insight': 'Esperando datos para analizar...',
        'recommendations': [],  # New field for recommendations
        'chart_image': None,
        'chart_data': [],
        'chart_labels': [],
        'chart_type': None,  # Initialize chart_type to prevent template errors
        'total_respuestas': 0,
        'estadisticas': None,
        'opciones': [],
        'options': [],  # Initialize options for template access
        'samples_texto': [],
        'top_options': [],
        'avg': None,
        'scale_cap': None,
    }