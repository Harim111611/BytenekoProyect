"""
ULTRA-OPTIMIZED SURVEY ANALYSIS ENGINE (V6 - GOD MODE: DEEP CONTEXT)
--------------------------------------------------------------------
Features:
- "Deep Narrative" Mode (4-line contextual insights).
- Strict Demographic Whitelist (Area, Ciudad, Edad, Pais).
- Aggressive PII Protection.
- Raw SQL Aggregations for Massive Performance.
"""

import logging
import re
import math
import random
import unicodedata
from collections import Counter, defaultdict
from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from core.utils.logging_utils import log_performance
from core.utils.charts import ChartGenerator

logger = logging.getLogger(__name__)

CACHE_TIMEOUT_ANALYSIS = 3600  # 1 hora

class AnalysisConstants:
    """Palabras comunes para ignorar en análisis de texto."""
    STOP_WORDS = {
        'este', 'esta', 'estas', 'estos', 'para', 'pero', 'porque', 'pues', 'solo', 'sobre', 'todo', 
        'que', 'con', 'los', 'las', 'una', 'uno', 'unos', 'unas', 'del', 'por', 'estoy', 'estan',
        'usted', 'ustedes', 'ellos', 'ellas', 'ser', 'son', 'era', 'eran', 'fue', 'fueron', 'muy', 'mas',
        'the', 'and', 'this', 'that', 'with', 'from', 'have', 'been', 'user_agent', 'browser', 'null', 'nan',
        'gracias', 'hola', 'adios', 'buenos', 'dias', 'tardes', 'noches', 'encuesta', 'respuesta', 'comentario'
    }

class SensitiveDataFilter:
    """
    Filtro de seguridad estricto.
    Solo permite demográficos autorizados y bloquea PII agresivamente.
    """
    
    # Lista BLANCA estricta de demográficos permitidos
    ALLOWED_DEMOGRAPHICS = {
        'area', 'departamento', 'gerencia', 'sector', # Variantes de AREA
        'ciudad', 'city', 'location', 'ubicacion', 'sede', # Variantes de CIUDAD
        'edad', 'age', 'rango etario', # Variantes de EDAD
        'pais', 'country', 'nacionalidad' # Variantes de PAIS
    }
    
    # Lista NEGRA de PII (Información Personal Identificable)
    PII_KEYWORDS = {
        'nombre', 'name', 'apellido', 'lastname', 'surname', 
        'email', 'correo', 'mail', 
        'telefono', 'phone', 'celular', 'mobile', 
        'rut', 'dni', 'cedula', 'passport', 'id', 'identificacion',
        'direccion', 'address', 'calle', 'domicilio',
        'tarjeta', 'credito', 'banco'
    }

    REGEX_EMAIL = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    
    @classmethod
    def analyze_question_metadata(cls, question):
        """Clasifica la pregunta según las reglas estrictas."""
        norm_text = normalize_text(question.text)
        tokens = set(norm_text.split())
        
        # 1. Metadatos Técnicos (Ignorar siempre)
        if any(k in norm_text for k in ['token', 'user_agent', 'ip_address', 'csrf']):
            return 'META', 'Metadato técnico'

        # 2. Protección PII (Prioridad Máxima)
        # Si contiene palabras prohibidas, es PII aunque el modelo diga que es demográfico
        if not tokens.isdisjoint(cls.PII_KEYWORDS):
            return 'PII', 'Datos personales detectados (Nombre/ID/Contacto)'

        # 3. Demografía Permitida (Lista Blanca)
        # Verificamos si alguna palabra clave coincide con los permitidos
        is_demo_model = getattr(question, 'is_demographic', False)
        matches_allowed = not tokens.isdisjoint(cls.ALLOWED_DEMOGRAPHICS)
        
        if is_demo_model or matches_allowed:
            return 'DEMO', 'Perfil Demográfico Autorizado'

        # 4. Por descarte, es una pregunta de opinión válida
        return 'VALID', 'Pregunta de opinión'

    @classmethod
    def sanitize_text_responses(cls, texts):
        """Borra emails de los textos libres."""
        cleaned = []
        for text in texts:
            if not text: continue
            text = re.sub(cls.REGEX_EMAIL, '[EMAIL OCULTO]', str(text))
            cleaned.append(text)
        return cleaned

class TextMiningEngine:
    """Extrae temas clave de textos."""
    @staticmethod
    def extract_topics(texts, top_n=5):
        words = []
        for text in texts:
            clean = normalize_text(text)
            tokens = [w for w in clean.split() if w not in AnalysisConstants.STOP_WORDS and len(w) > 3]
            if tokens:
                words.extend(tokens)
                if len(tokens) > 1:
                    bigrams = [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens)-1)]
                    words.extend(bigrams)
        
        if not words: return "No hay suficiente texto para analizar."
        
        common = Counter(words).most_common(top_n)
        return ", ".join([f"<strong>{c[0]}</strong>" for c in common])

class InsightEngine:
    """
    Generador de Narrativa Contextual Profunda (4 Líneas).
    """

    CONTEXTS = {
        'TIEMPO': {'tiempo', 'demora', 'espera', 'tardanza', 'rapidez', 'velocidad', 'lento', 'agilidad', 'minutos'},
        'ATENCION': {'atencion', 'amabilidad', 'trato', 'personal', 'staff', 'soporte', 'ayuda', 'cortesia'},
        'CALIDAD': {'calidad', 'limpieza', 'estado', 'funcionamiento', 'sabor', 'confort', 'instalaciones'},
        'PRECIO': {'precio', 'costo', 'valor', 'pagar', 'caro', 'barato', 'economico'},
        'FACILIDAD': {'facilidad', 'dificultad', 'uso', 'app', 'sistema', 'proceso', 'tramite'}
    }

    # Bloques de construcción narrativa
    
    # LÍNEA 1: La Apertura (Estado emocional / Situación actual)
    OPENINGS = {
        'EXCELENTE': [
            "Nos encontramos en una posición de liderazgo absoluto en este aspecto.",
            "Los resultados aquí son motivo de celebración para el equipo.",
            "La percepción del usuario supera ampliamente las expectativas.",
            "Estamos marcando un estándar de excelencia difícil de igualar."
        ],
        'BUENO': [
            "Tenemos una base sólida y saludable, aunque con espacio para crecer.",
            "La mayoría de los usuarios aprueba nuestro desempeño actual.",
            "Estamos cumpliendo la promesa básica, pero sin llegar a sorprender.",
            "El sentimiento general es positivo y vamos por buen camino."
        ],
        'REGULAR': [
            "Detectamos señales de fricción que no debemos ignorar.",
            "El desempeño es inconstante y genera dudas en el usuario.",
            "Estamos en una zona de riesgo donde la experiencia no convence.",
            "Hay una brecha evidente entre lo que ofrecemos y lo esperado."
        ],
        'CRITICO': [
            "Esta es una zona roja que está dañando nuestra reputación.",
            "La insatisfacción es alta y requiere intervención inmediata.",
            "Estamos fallando en un punto crítico para el usuario.",
            "Las alertas están encendidas: la experiencia aquí es deficiente."
        ]
    }

    # LÍNEA 2: La Evidencia (Datos + Tendencia)
    EVIDENCE_TEMPLATES = {
        'UP': "El promedio de <strong>{avg:.1f}/{scale}</strong> muestra una recuperación reciente, indicando que las correcciones están funcionando.",
        'DOWN': "Aunque el promedio es <strong>{avg:.1f}/{scale}</strong>, la tendencia reciente es negativa, lo que sugiere un deterioro progresivo.",
        'STABLE': "El indicador se mantiene estable en <strong>{avg:.1f}/{scale}</strong>, consolidando una tendencia histórica sin sobresaltos."
    }

    # LÍNEA 3: El Consenso (Profundidad social)
    CONSENSUS_TEMPLATES = {
        'HIGH_AGREEMENT': "Lo notable es que casi todos opinan lo mismo, lo que confirma que la experiencia es consistente para todos.",
        'POLARIZED': "Sin embargo, vemos una fuerte división: mientras un grupo está feliz, otro está muy molesto (polarización).",
        'NORMAL': "La distribución de opiniones es normal y esperada, sin grupos extremos que distorsionen el análisis."
    }

    # LÍNEA 4: La Estrategia (Call to Action)
    STRATEGY_TEMPLATES = {
        'QUICK_WIN': "💡 <strong>Estrategia:</strong> Al ser fácil de mejorar, enfócate aquí para obtener una victoria rápida y subir el ánimo.",
        'CRITICAL': "🚨 <strong>Estrategia:</strong> Prioridad 1. Asigna recursos urgentes para investigar la causa raíz y frenar la caída.",
        'MAINTAIN': "✨ <strong>Estrategia:</strong> Documenta lo que hacen bien aquí y replica estas buenas prácticas en otras áreas.",
        'WATCH': "👀 <strong>Estrategia:</strong> No requiere acción urgente, pero agrégalo a la lista de vigilancia mensual."
    }

    @classmethod
    def analyze_metrics(cls, question_text, stats, dist_data, scale_cap, trend_delta=0, question_id=None):
        # Seed para que el texto sea consistente al recargar
        rng = random.Random(question_id or stats['avg'])
        context = cls._detect_context(question_text)
        
        avg = stats['avg']
        count = stats['count']
        
        # 1. Análisis Estadístico
        std_dev = cls._calculate_std_dev(dist_data, avg, count)
        score_10, lower_is_better = cls._normalize_score(avg, scale_cap, context, question_text)
        mood = cls._determine_mood(score_10)

        # 2. Determinación de Tendencia
        trend_key = 'STABLE'
        if abs(trend_delta) > 0.05:
            is_good = (trend_delta < 0) if lower_is_better else (trend_delta > 0)
            trend_key = 'UP' if is_good else 'DOWN'

        # 3. Determinación de Consenso
        consensus_key = 'NORMAL'
        if scale_cap > 0:
            if std_dev > (scale_cap * 0.22): consensus_key = 'POLARIZED'
            elif std_dev < (scale_cap * 0.12): consensus_key = 'HIGH_AGREEMENT'

        # 4. Selección de Estrategia
        strategy_key = 'WATCH'
        if mood in ['CRITICO', 'REGULAR']:
            strategy_key = 'CRITICAL' if trend_key == 'DOWN' else 'QUICK_WIN'
        elif mood == 'EXCELENTE':
            strategy_key = 'MAINTAIN'

        # --- ENSAMBLAJE DEL PÁRRAFO ---
        line_1 = rng.choice(cls.OPENINGS[mood])
        line_2 = cls.EVIDENCE_TEMPLATES[trend_key].format(avg=avg, scale=scale_cap)
        line_3 = cls.CONSENSUS_TEMPLATES[consensus_key]
        line_4 = cls.STRATEGY_TEMPLATES[strategy_key]

        html = f"""
            <div class='analysis-card p-3 analysis-card-{mood.lower()}'>
                <p class='mb-1 text-dark'>{line_1}</p>
                <p class='mb-1 text-muted'>{line_2}</p>
                <p class='mb-2 text-muted'>{line_3}</p>
                <div class='mt-2 pt-2 border-top analysis-card-footer'>
                    {line_4}
                </div>
            </div>
        """

        return {
            'state': mood,
            'insight': html,
            'score_norm': round(score_10, 1)
        }

    @staticmethod
    def _detect_context(text):
        norm = normalize_text(text)
        tokens = set(norm.split())
        for ctx, keywords in InsightEngine.CONTEXTS.items():
            if not tokens.isdisjoint(keywords): return ctx
        return 'GENERAL'

    @staticmethod
    def _calculate_std_dev(dist_data, avg, count):
        if count <= 1: return 0
        sum_sq = sum(d['count'] * ((d['value'] - avg) ** 2) for d in dist_data)
        return math.sqrt(sum_sq / (count - 1))

    @staticmethod
    def _normalize_score(avg, scale_cap, context, text):
        norm_text = normalize_text(text)
        lower_is_better = False
        if context == 'TIEMPO' and not any(k in norm_text for k in ['satisfaccion', 'calificacion']):
            lower_is_better = True
        elif 'precio' in norm_text and 'caro' in norm_text:
            lower_is_better = True
        
        score = (avg / scale_cap) * 10 if scale_cap > 0 else 0
        final_score = (10 - score) if lower_is_better else score
        return final_score, lower_is_better

    @staticmethod
    def _determine_mood(score):
        if score >= 8.5: return 'EXCELENTE'
        if score >= 7.0: return 'BUENO'
        if score >= 5.0: return 'REGULAR'
        return 'CRITICO'
        
    @staticmethod
    def _get_color(mood):
        return {'EXCELENTE': '#198754', 'BUENO': '#0d6efd', 'REGULAR': '#ffc107', 'CRITICO': '#dc3545'}.get(mood, '#6c757d')


def normalize_text(text):
    if not text: return ''
    text_str = str(text)
    text_str = text_str.translate(str.maketrans('', '', '¿?¡!_-.[](){}:,"'))
    normalized = unicodedata.normalize('NFKD', text_str).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', normalized).strip().lower()


class SurveyAnalysisService:
    """
    Servicio Maestro Orquestador.
    """

    @staticmethod
    @log_performance(threshold_ms=2500)
    def get_analysis_data(survey, responses_queryset, include_charts=True, cache_key=None, use_base_filter=True, dark_mode=False):
        # 1. Cache Inteligente
        if cache_key is None:
            last_id = responses_queryset.order_by('-id').values_list('id', flat=True).first() or 0
            cache_key = f"survey_godmode_v6:{survey.id}:{responses_queryset.count()}:{last_id}"
        
        cached = cache.get(cache_key)
        if cached: return cached

        # 2. Configuración
        analysis_data = []
        questions = list(survey.questions.prefetch_related('options').order_by('order'))
        
        numeric_stats = {}
        numeric_dist = defaultdict(list)
        choice_dist = defaultdict(list)
        text_responses = defaultdict(list)
        trend_stats = {} 
        
        # 3. Clasificación de Preguntas (Valid, PII, Demo)
        analyzable_q = []
        skipped_log = []

        for q in questions:
            cat, reason = SensitiveDataFilter.analyze_question_metadata(q)
            
            if cat == 'META': 
                skipped_log.append({'id': q.id, 'text': q.text, 'reason': reason})
            elif cat == 'PII': 
                # PROTECCIÓN TOTAL: Se ignora visualmente, solo se reporta que existió
                skipped_log.append({'id': q.id, 'text': q.text, 'reason': f'🛡️ PII Bloqueado: {reason}'})
            else:
                # Tanto DEMO como VALID pasan al análisis
                q.analysis_category = cat
                analyzable_q.append(q)

        if not analyzable_q:
             return SurveyAnalysisService._build_empty_response(skipped_log)

        # 4. Construcción SQL Optimizado
        try:
            query = responses_queryset.values('id').query
            sql, params = query.get_compiler(using=responses_queryset.db).as_sql()
            base_where = f" AND survey_response_id IN ({sql})"
            base_params = params
        except Exception as e:
            logger.error(f"SQL Error: {e}")
            return SurveyAnalysisService._build_empty_response(skipped_log)

        # 5. Ejecución SQL
        with connection.cursor() as cursor:
            # A. Numéricos
            num_ids = [q.id for q in analyzable_q if q.type in {'scale', 'number'}]
            if num_ids:
                ids_ph = ','.join(['%s'] * len(num_ids))
                # Stats
                cursor.execute(f"""
                    SELECT question_id, COUNT(*), AVG(numeric_value), MAX(numeric_value)
                    FROM surveys_questionresponse 
                    WHERE question_id IN ({ids_ph}) AND numeric_value IS NOT NULL {base_where}
                    GROUP BY question_id
                """, num_ids + list(base_params))
                for row in cursor.fetchall():
                    numeric_stats[row[0]] = {'count': row[1], 'avg': row[2], 'max': row[3]}

                # Distribución
                cursor.execute(f"""
                    SELECT question_id, numeric_value, COUNT(*)
                    FROM surveys_questionresponse
                    WHERE question_id IN ({ids_ph}) AND numeric_value IS NOT NULL {base_where}
                    GROUP BY question_id, numeric_value
                """, num_ids + list(base_params))
                for row in cursor.fetchall():
                    numeric_dist[row[0]].append({'value': row[1], 'count': row[2]})
                
                # Tendencia (Last 50)
                cursor.execute(f"""
                    SELECT question_id, AVG(numeric_value)
                    FROM (
                        SELECT question_id, numeric_value,
                               ROW_NUMBER() OVER (PARTITION BY question_id ORDER BY id DESC) as rn
                        FROM surveys_questionresponse
                        WHERE question_id IN ({ids_ph}) AND numeric_value IS NOT NULL {base_where}
                    ) as recent_data
                    WHERE rn <= 50 
                    GROUP BY question_id
                """, num_ids + list(base_params))
                for row in cursor.fetchall():
                    trend_stats[row[0]] = row[1]

            # B. Categorías
            cat_ids = [q.id for q in analyzable_q if q.type in {'single', 'multi'}]
            if cat_ids:
                ids_ph = ','.join(['%s'] * len(cat_ids))
                cursor.execute(f"""
                    SELECT qr.question_id, ao.text, COUNT(*)
                    FROM surveys_questionresponse qr
                    JOIN surveys_answeroption ao ON qr.selected_option_id = ao.id
                    WHERE qr.question_id IN ({ids_ph}) {base_where.replace('survey_response_id', 'qr.survey_response_id')}
                    GROUP BY qr.question_id, ao.text
                """, cat_ids + list(base_params))
                for row in cursor.fetchall():
                    choice_dist[row[0]].append({'option': row[1], 'count': row[2]})

            # C. Texto
            txt_ids = [q.id for q in analyzable_q if q.type == 'text']
            if txt_ids:
                ids_ph = ','.join(['%s'] * len(txt_ids))
                cursor.execute(f"""
                    SELECT question_id, text_value
                    FROM surveys_questionresponse
                    WHERE question_id IN ({ids_ph}) AND text_value <> '' {base_where}
                """, txt_ids + list(base_params))
                limit_per_q = 150
                counts = defaultdict(int)
                for row in cursor.fetchall():
                    if counts[row[0]] < limit_per_q:
                        text_responses[row[0]].append(row[1])
                        counts[row[0]] += 1

        # 6. Procesamiento Final
        satisfaction_scores = []
        
        for idx, q in enumerate(analyzable_q, 1):
            item = SurveyAnalysisService._init_item(q, idx)
            qid = q.id
            is_demo = getattr(q, 'analysis_category', 'VALID') == 'DEMO'
            item['is_demographic'] = is_demo
            
            # --- Numérico ---
            if qid in numeric_stats:
                stats = numeric_stats[qid]
                item.update(stats)
                item['total_respuestas'] = stats['count']
                scale_cap = 10 if stats['max'] > 5 else 5
                
                dist = sorted(numeric_dist.get(qid, []), key=lambda x: x['value'])
                item['chart_labels'] = [str(int(d['value'])) for d in dist]
                item['chart_data'] = [d['count'] for d in dist]
                
                trend_avg = trend_stats.get(qid, stats['avg'])
                delta = 0
                if stats['avg'] > 0:
                    delta = (trend_avg - stats['avg']) / stats['avg']

                if is_demo:
                    # Contexto especial para demografía numérica (Edad)
                    item['insight'] = f"""
                        <div class='analysis-card p-3'>
                            <p class='mb-1'><strong>Perfil Demográfico:</strong> Análisis de Edad.</p>
                            <p class='text-muted'>El promedio de edad es {stats['avg']:.1f} años.</p>
                        </div>
                    """
                else:
                    # CONTEXTO COMPLETO 4 LÍNEAS
                    insight_obj = InsightEngine.analyze_metrics(
                        q.text, stats, dist, scale_cap, trend_delta=delta, question_id=qid
                    )
                    item['state'] = insight_obj['state']
                    item['insight'] = insight_obj['insight']
                    satisfaction_scores.append(stats['avg'])
                
                if include_charts and item['chart_data']:
                    item['chart_image'] = ChartGenerator.generate_vertical_bar_chart(item['chart_labels'], item['chart_data'], "Distribución", dark_mode=dark_mode)

            # --- Categorías ---
            elif qid in choice_dist:
                dist = sorted(choice_dist[qid], key=lambda x: x['count'], reverse=True)
                total = sum(d['count'] for d in dist)
                item['total_respuestas'] = total
                
                top_n = dist[:10]
                item['chart_labels'] = [d['option'] for d in top_n]
                item['chart_data'] = [d['count'] for d in top_n]
                item['options'] = [{'label': d['option'], 'count': d['count'], 'percent': round(d['count']*100/total if total else 0, 1)} for d in dist]
                
                if dist:
                    top = dist[0]
                    pct = item['options'][0]['percent']
                    
                    if is_demo:
                        # Contexto demográfico
                        msg = f"""
                            <div class='analysis-card p-3'>
                                <p class='mb-1'><strong>Perfil Demográfico ({q.text}):</strong></p>
                                <p class='text-muted'>El grupo mayoritario pertenece a <strong>{top['option']}</strong>, representando el {pct}% de la muestra.</p>
                            </div>
                        """
                        item['insight'] = msg
                    else:
                        # Contexto categórico de opinión
                        item['insight'] = f"""
                            <div class='analysis-card p-3'>
                                <p class='mb-1'>La preferencia dominante es clara.</p>
                                <p class='text-muted'>El {pct}% de los encuestados eligió <strong>{top['option']}</strong>.</p>
                                <p class='text-muted small mt-2'>Esto define la tendencia principal del grupo.</p>
                            </div>
                        """
                    
                if include_charts and item['chart_data']:
                    title = "Perfil" if is_demo else "Resultados"
                    if len(top_n) <= 6:
                        item['chart_image'] = ChartGenerator.generate_pie_chart(item['chart_labels'], item['chart_data'], title, dark_mode=dark_mode)
                    else:
                        item['chart_image'] = ChartGenerator.generate_horizontal_bar_chart(item['chart_labels'], item['chart_data'], title, dark_mode=dark_mode)

            # --- Texto ---
            elif qid in text_responses:
                raw_texts = text_responses[qid]
                clean_texts = SensitiveDataFilter.sanitize_text_responses(raw_texts)
                item['total_respuestas'] = len(clean_texts)
                item['samples_texto'] = clean_texts[:5]
                
                topics_html = TextMiningEngine.extract_topics(clean_texts)
                item['insight'] = f"""
                    <div class='analysis-card p-3'>
                        <p class='mb-2'><strong>Análisis de Texto:</strong></p>
                        <p class='text-muted'>Los temas más repetidos en los comentarios son:</p>
                        <div class='mt-2'>{topics_html}</div>
                    </div>
                """
            
            analysis_data.append(item)

        kpi_score = sum(satisfaction_scores)/len(satisfaction_scores) if satisfaction_scores else 0

        result = {
            'analysis_data': analysis_data,
            'kpi_prom_satisfaccion': kpi_score,
            'ignored_questions': skipped_log,
            'meta': {'generated_at': timezone.now().isoformat()}
        }
        
        cache.set(cache_key, result, CACHE_TIMEOUT_ANALYSIS)
        return result

    @staticmethod
    def _build_empty_response(skipped):
        return {'analysis_data': [], 'ignored_questions': skipped}

    @staticmethod
    def _init_item(q, order):
        return {
            'id': q.id, 'text': q.text, 'type': q.type, 'order': order,
            'tipo_display': q.get_type_display(), 'insight': '', 
            'options': [], 'chart_data': []
        }