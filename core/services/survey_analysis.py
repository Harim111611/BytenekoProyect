"""core/services/survey_analysis.py"""
import logging
import math
import re
import random
import unicodedata
from collections import defaultdict, Counter
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from core.utils.logging_utils import log_performance

logger = logging.getLogger(__name__)
CACHE_TIMEOUT_ANALYSIS = 3600

# --- 1. UTILIDADES Y CONSTANTES ---

class NarrativeUtils:
    @staticmethod
    def get_template(key, templates_dict, seed_source):
        """Selecciona una plantilla variada basada en el ID."""
        options = templates_dict.get(key, ["Sin análisis disponible."])
        rng = random.Random(seed_source)
        return rng.choice(options)

class AnalysisConstants:
    STOP_WORDS = {
        'este', 'esta', 'estas', 'estos', 'para', 'pero', 'porque', 'pues', 'solo', 'sobre', 'todo', 
        'que', 'con', 'los', 'las', 'una', 'uno', 'unos', 'unas', 'del', 'por', 'estoy', 'estan',
        'usted', 'ustedes', 'ellos', 'ellas', 'ser', 'son', 'era', 'eran', 'fue', 'fueron', 'muy', 'mas',
        'the', 'and', 'this', 'that', 'with', 'from', 'have', 'been', 'user_agent', 'browser', 'null', 'nan',
        'gracias', 'hola', 'adios', 'buenos', 'dias', 'tardes', 'noches', 'encuesta', 'respuesta', 'comentario',
        'bien', 'mal', 'regular', 'excelente', 'bueno', 'malo', 'satisfecho', 'servicio', 'si', 'no', 'mi', 'me'
    }

def normalize_text(text):
    if not text: return ''
    text_str = str(text)
    text_str = text_str.translate(str.maketrans('', '', '¿?¡!_-.[](){}:,"'))
    normalized = unicodedata.normalize('NFKD', text_str).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', normalized).strip().lower()

# --- 2. MOTORES DE NARRATIVA ESPECIALIZADA (VERSIÓN EXTENDIDA) ---

class DemographicNarrative:
    """
    Motor de análisis demográfico con capacidad de redacción extendida.
    Genera párrafos completos que explican el contexto de los datos.
    """
    
    # --- PLANTILLAS GENÉRICAS (Para cualquier pregunta de opción) ---
    GENERIC_TEMPLATES = {
        'UNANIMOUS': [
            "Existe un consenso prácticamente absoluto en este punto. La opción **{top1}** domina el panorama con un contundente {pct1:.1f}% de las preferencias, dejando al resto de alternativas como marginales. Esto sugiere una alineación total de la audiencia.",
            "Resultados concluyentes: **{top1}** es la elección indiscutible de la muestra ({pct1:.1f}%). La falta de dispersión en las respuestas indica que no existen dudas significativas respecto a este tema."
        ],
        'DOMINANT': [
            "Se observa una tendencia mayoritaria clara hacia **{top1}**, que aglutina al {pct1:.1f}% de los encuestados. Aunque existen otras opiniones, este grupo define la pauta principal del comportamiento de la muestra.",
            "La preferencia por **{top1}** es evidente, superando con creces a las demás opciones. Con más de la mitad de los votos ({pct1:.1f}%), esta opción se consolida como el estándar dentro del grupo analizado."
        ],
        'DUAL': [
            "El escenario se encuentra polarizado. La opinión pública se divide principalmente en dos frentes: **{top1}** y **{top2}**, que en conjunto suman el {sum_pct:.1f}% del total. Será clave entender qué factores inclinan la balanza hacia uno u otro lado.",
            "No hay un líder único. La audiencia muestra una dicotomía marcada entre **{top1}** ({pct1:.1f}%) y **{top2}** ({pct2:.1f}%). Esta competencia directa sugiere que existen dos perfiles de usuario o necesidades muy diferenciadas."
        ],
        'COMPETITIVE': [
            "Nos encontramos ante una competencia reñida sin un ganador hegemónico. Aunque **{top1}** lidera ligeramente, **{top2}** y las opciones subsecuentes mantienen cuotas relevantes, lo que indica diversidad de criterios en la muestra.",
            "El panorama es fragmentado y competitivo. La diferencia entre **{top1}** y **{top2}** es poco significativa, lo que denota una audiencia heterogénea con preferencias muy variadas."
        ]
    }

    # --- PLANTILLAS DE EDAD (Detecta juventud, madurez, etc.) ---
    AGE_TEMPLATES = {
        'YOUNG': [
            "El perfil demográfico es eminentemente joven. El predominio del rango **{top1}** ({pct1:.1f}%) sugiere una audiencia en etapas tempranas (estudiantes o primeros empleos), lo que favorece estrategias digitales, dinámicas y de rápida adopción.",
            "Estamos ante una 'Generación Nueva'. La concentración en **{top1}** indica que el servicio resuena principalmente con usuarios jóvenes. Es vital adaptar el lenguaje y los canales de comunicación a este segmento nativo digital."
        ],
        'MATURE': [
            "La muestra exhibe un perfil de madurez consolidada. El grueso de la población se ubica en **{top1}** ({pct1:.1f}%), un segmento usualmente caracterizado por mayor estabilidad financiera y toma de decisiones más racional.",
            "El núcleo de la audiencia es adulto/maduro, liderado por el grupo de **{top1}**. Esto sugiere enfocarse en propuestas de valor que prioricen la calidad, la fiabilidad y el largo plazo sobre la inmediatez."
        ],
        'SENIOR': [
            "Tendencia clara hacia segmentos senior. Con **{top1}** como grupo mayoritario ({pct1:.1f}%), es fundamental priorizar la accesibilidad, la claridad en la información y un servicio al cliente más tradicional y cercano.",
            "La base de usuarios tiende a la tercera edad o segmentos senior (**{top1}**). Estratégicamente, esto implica que la confianza y la simplicidad de uso son los drivers más importantes para este grupo."
        ],
        'MIXED': [
            "Diversidad generacional amplia. Conviven grupos de **{top1}** y **{top2}** de manera significativa. Esta mezcla exige una estrategia segmentada, ya que no existe un enfoque de 'talla única' para toda la muestra.",
            "Intersección de generaciones. Los datos muestran un equilibrio entre **{top1}** y **{top2}**, lo que sugiere que el producto/servicio tiene un atractivo transversal que cruza barreras de edad."
        ]
    }

    # --- PLANTILLAS DE UBICACIÓN ---
    LOCATION_TEMPLATES = {
        'CONCENTRATED': [
            "Fuerte centralización geográfica. La zona de **{top1}** concentra el {pct1:.1f}% de la actividad, lo que convierte al proyecto en un fenómeno local o muy focalizado. Se recomienda saturar este mercado antes de expandirse.",
            "El alcance es principalmente regional, con **{top1}** dominando la muestra. Las estrategias deben considerar las particularidades culturales y logísticas de esta ubicación específica."
        ],
        'DISPERSED': [
            "Alta dispersión territorial. Aunque **{top1}** aparece en primer lugar, su peso es diluido frente a la suma de otras ubicaciones. Esto indica un alcance nacional o multi-regional que requiere logística distribuida.",
            "La huella geográfica es amplia. No dependemos de una sola ubicación, ya que el liderazgo de **{top1}** no es absoluto. Esto es positivo para la resiliencia del negocio, pero complejo operativamente."
        ],
        'DUAL_HUB': [
            "Bipolaridad geográfica. La actividad se ancla en dos grandes polos: **{top1}** y **{top2}**. La estrategia debe tratarse como un corredor entre estos dos hubs principales.",
            "Dos centros de gravedad definen la muestra: **{top1}** y **{top2}**. Es recomendable crear campañas o logísticas diferenciadas para estos dos mercados clave."
        ]
    }

    # --- PLANTILLAS DE GÉNERO ---
    GENDER_TEMPLATES = {
        'BALANCED': [
            "Paridad de género notable. La distribución es prácticamente simétrica entre **{top1}** y **{top2}**. Esto valida que la propuesta de valor es inclusiva y transversal.",
            "Equilibrio demográfico. No se observa sesgo de género, con una participación equitativa de **{top1}** y **{top2}**."
        ],
        'SKEWED': [
            "El perfil tiene un sesgo de género marcado hacia **{top1}** ({pct1:.1f}%), existiendo una brecha significativa. Esto puede ser intencional (nicho) o una señal de que el mensaje no está llegando al otro segmento.",
            "Predominancia clara de **{top1}** en la muestra. Si el producto es unisex, convendría revisar por qué no está atrayendo a los otros grupos con la misma fuerza."
        ]
    }

    @staticmethod
    def analyze(dist, total, question, seed):
        if not dist or total == 0: return "No se dispone de suficientes datos para elaborar un análisis demográfico fiable."
        
        # 1. Preparar datos
        sorted_dist = sorted(dist, key=lambda x: x['count'], reverse=True)
        top1 = sorted_dist[0]
        top1_pct = (top1['count'] / total) * 100
        
        top2 = sorted_dist[1] if len(sorted_dist) > 1 else None
        top2_pct = (top2['count'] / total) * 100 if top2 else 0
        
        sum_top2 = top1_pct + top2_pct

        # 2. Detectar Tipo Demográfico (Inteligencia contextual)
        dtype = getattr(question, 'demographic_type', None)
        text_lower = normalize_text(question.text)
        
        # Inferencia si no está explícito en el modelo
        if not dtype:
            if any(x in text_lower for x in ['edad', 'rango', 'anios', 'años', 'nacimiento']): dtype = 'age'
            elif any(x in text_lower for x in ['genero', 'sexo', 'mujer', 'hombre', 'masculino']): dtype = 'gender'
            elif any(x in text_lower for x in ['ciudad', 'estado', 'pais', 'donde vives', 'ubicacion', 'residencia']): dtype = 'location'
            elif any(x in text_lower for x in ['civil', 'soltero', 'casado', 'pareja']): dtype = 'marital_status'

        # 3. Selección de Estrategia Narrativa
        tmpl_dict = DemographicNarrative.GENERIC_TEMPLATES
        key = 'COMPETITIVE'

        # --- Lógica EDAD ---
        if dtype == 'age':
            tmpl_dict = DemographicNarrative.AGE_TEMPLATES
            opt_text = normalize_text(top1['option'])
            # Heurística para detectar rangos en el texto de la opción
            if any(x in opt_text for x in ['18', '20', '24', '25', '30', 'joven', 'estudiante']): key = 'YOUNG'
            elif any(x in opt_text for x in ['60', '65', 'mas', 'mayor', 'jubilado', 'senior']): key = 'SENIOR'
            elif sum_top2 < 60: key = 'MIXED'
            else: key = 'MATURE'

        # --- Lógica UBICACIÓN ---
        elif dtype == 'location':
            tmpl_dict = DemographicNarrative.LOCATION_TEMPLATES
            if top1_pct > 60: key = 'CONCENTRATED'
            elif top2 and (top1_pct - top2_pct < 15): key = 'DUAL_HUB'
            else: key = 'DISPERSED'

        # --- Lógica GÉNERO ---
        elif dtype == 'gender':
            tmpl_dict = DemographicNarrative.GENDER_TEMPLATES
            if abs(top1_pct - top2_pct) < 15: key = 'BALANCED'
            else: key = 'SKEWED'

        # --- Lógica ESTADO CIVIL (Usa genérico adaptado o se puede crear uno propio si se desea) ---
        # Por ahora usaremos el genérico para marital status pero detectando dominancia

        # --- Lógica GENÉRICA (Fallback) ---
        if dtype not in ['age', 'location', 'gender']:
            if top1_pct >= 80: key = 'UNANIMOUS'
            elif top1_pct >= 55: key = 'DOMINANT'
            elif top2 and (top1_pct - top2_pct) < 15 and sum_top2 > 60: key = 'DUAL'
            else: key = 'COMPETITIVE'

        # 4. Renderizado Final
        tmpl = NarrativeUtils.get_template(key, tmpl_dict, seed)
        return tmpl.format(
            top1=top1['option'], 
            pct1=top1_pct,
            top2=top2['option'] if top2 else 'la segunda opción',
            pct2=top2_pct,
            sum_pct=sum_top2
        )

class MetricNarrative:
    """Motor de análisis para métricas numéricas (Satisfacción, NPS)."""
    
    TEMPLATES = {
        'PERFECT': [
            "Rendimiento excepcional. Con un promedio de **{avg:.1f}**, los indicadores rozan la perfección. Es extremadamente raro ver niveles de aprobación tan altos, lo que confirma un 'Product-Market Fit' ideal.",
            "Liderazgo total en este rubro. La calificación casi perfecta (**{avg:.1f}**) sugiere que las expectativas de los usuarios no solo se cumplen, sino que se superan sistemáticamente."
        ],
        'EXCELLENT': [
            "Desempeño sobresaliente. El resultado de **{avg:.1f}** es altamente positivo y sitúa a este aspecto como una de las grandes fortalezas del proyecto. La percepción de valor es muy clara.",
            "Fortaleza consolidada. La gran mayoría de la muestra califica positivamente este aspecto (**{avg:.1f}**), lo que genera una base sólida de promotores leales para la marca."
        ],
        'GOOD': [
            "Buen desempeño general (**{avg:.1f}**), aunque existe margen para la optimización. Es un indicador saludable, aprobado por la mayoría, pero que requiere vigilancia para no estancarse.",
            "Resultado positivo y estable. La calificación de **{avg:.1f}** indica satisfacción, pero no deleite. Es un buen punto de partida para iterar y buscar la excelencia."
        ],
        'POLARIZED': [
            "¡Cuidado con el promedio! Aunque el número final es **{avg:.1f}**, detectamos una fuerte polarización. Hay grupos que aman la propuesta y otros que la rechazan. El promedio esconde esta división crítica.",
            "Opiniones extremas detectadas. La audiencia está dividida: un grupo otorga puntajes muy altos y otro muy bajos. Esto sugiere que la propuesta de valor no es universal o tiene fallos graves para un segmento específico."
        ],
        'REGULAR': [
            "Zona de oportunidad clara. El desempeño es variable (**{avg:.1f}**), lo que indica que la experiencia no es consistente para todos los usuarios. Se recomienda revisar procesos.",
            "Resultados mixtos (**{avg:.1f}**). No se logra convencer plenamente a una parte significativa de la muestra. Es necesario investigar cualitativamente qué está frenando una mejor calificación."
        ],
        'CRITICAL': [
            "Alerta roja: Punto de dolor crítico. El promedio de **{avg:.1f}** revela una insatisfacción estructural. Urge intervención inmediata antes de que este factor dañe la reputación general.",
            "Evaluación negativa predominante (**{avg:.1f}**). Los usuarios están enviando un mensaje claro de que este aspecto no cumple con los mínimos esperados. Requiere reingeniería urgente."
        ]
    }

    @staticmethod
    def analyze(stats, dist, scale_max, seed):
        avg = stats['avg']
        count = stats['count']
        if count < 5: return "Datos insuficientes para un análisis estadístico robusto.", "NEUTRO"

        max_val = scale_max or 10
        score = (avg / max_val) * 10
        
        # Detección de Polarización (Bimodalidad)
        low_bucket = sum(d['count'] for d in dist if d['value'] <= (max_val * 0.3))
        high_bucket = sum(d['count'] for d in dist if d['value'] >= (max_val * 0.7))
        
        # Si más del 25% está en el fondo y más del 25% en el tope -> Polarizado
        is_polarized = (low_bucket > count * 0.25) and (high_bucket > count * 0.25)

        mood = 'NEUTRO'
        key = 'REGULAR'

        if is_polarized:
            key = 'POLARIZED'
            mood = 'WARNING'
        elif score >= 9.2:
            key, mood = 'PERFECT', 'EXCELENTE'
        elif score >= 8.0:
            key, mood = 'EXCELLENT', 'EXCELENTE'
        elif score >= 7.0:
            key, mood = 'GOOD', 'BUENO'
        elif score >= 5.0:
            key, mood = 'REGULAR', 'REGULAR'
        else:
            key, mood = 'CRITICAL', 'CRITICO'

        text = NarrativeUtils.get_template(key, MetricNarrative.TEMPLATES, seed)
        
        # Inyectamos el promedio en el texto seleccionado
        return text.format(avg=avg), mood

class SensitiveDataFilter:
    PII_KEYWORDS = {'nombre', 'name', 'apellido', 'email', 'telefono', 'celular', 'rut', 'dni', 'direccion', 'tarjeta', 'cvv'}
    
    @classmethod
    def analyze_question_metadata(cls, question):
        norm_text = str(question.text).lower()
        if any(k in norm_text for k in ['token', 'user_agent', 'ip_address']): return 'META', 'Metadato técnico'
        
        tokens = set(re.findall(r'\w+', norm_text))
        if not tokens.isdisjoint(cls.PII_KEYWORDS): return 'PII', 'Posible dato personal'
        if getattr(question, 'is_demographic', False): return 'DEMO', 'Demográfico'
        return 'VALID', 'Opinión'

    @classmethod
    def sanitize_text_responses(cls, texts):
        clean_texts = []
        for t in texts:
            if not t: continue
            s = str(t)
            s = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[EMAIL]', s)
            s = re.sub(r'\b\d{8,}\b', '[TEL]', s)
            clean_texts.append(s)
        return clean_texts

class TextMiningEngine:
    @staticmethod
    def extract_topics(texts):
        words = []
        for text in texts:
            clean = normalize_text(text)
            tokens = [w for w in clean.split() if w not in AnalysisConstants.STOP_WORDS and len(w) > 3]
            words.extend(tokens)
        if not words: return []
        return [item[0] for item in Counter(words).most_common(6)]

class TimelineEngine:
    @staticmethod
    def analyze_evolution(survey, qs, questions):
        dates = list(qs.values_list('created_at', flat=True))
        counts = defaultdict(int)
        for dt in dates:
            if dt: counts[dt.date()] += 1
        sorted_dates = sorted(counts.keys())
        return {
            'labels': [d.strftime('%d/%m') for d in sorted_dates],
            'data': [counts[d] for d in sorted_dates],
            'source': 'SYSTEM'
        }

# --- 3. SERVICIO PRINCIPAL ---

class SurveyAnalysisService:
    @staticmethod
    @log_performance(threshold_ms=2500)
    def get_analysis_data(survey, responses_queryset, include_charts=True, cache_key=None, dark_mode=False):
        total = responses_queryset.count()
        if cache_key is None:
            last_id = responses_queryset.order_by('-id').values_list('id', flat=True).first() or 0
            cache_key = f"analysis_expert_v1:{survey.id}:{total}:{last_id}"

        cached = cache.get(cache_key)
        if cached: return cached

        questions = list(survey.questions.prefetch_related('options').order_by('order'))
        analysis_data = []
        skipped_log = []
        analyzable_q = []

        for q in questions:
            cat, reason = SensitiveDataFilter.analyze_question_metadata(q)
            q.analysis_category = cat
            if cat in ('PII', 'META'):
                skipped_log.append({'id': q.id, 'text': q.text, 'reason': reason})
            else:
                analyzable_q.append(q)

        if not analyzable_q or total == 0:
            return SurveyAnalysisService._build_empty_response(skipped_log)

        numeric_stats, numeric_dist, trend_stats = SurveyAnalysisService._fetch_numeric_stats(analyzable_q, responses_queryset)
        choice_dist = SurveyAnalysisService._fetch_choice_stats(analyzable_q, responses_queryset)
        text_responses = SurveyAnalysisService._fetch_text_responses(analyzable_q, responses_queryset)
        
        satisfaction_scores = []

        for idx, q in enumerate(analyzable_q, 1):
            item = {
                'id': q.id, 'text': q.text, 'type': q.type, 'order': idx,
                'is_demographic': (q.analysis_category == 'DEMO'),
                'insight_data': {}
            }
            
            # --- Numérico ---
            if q.id in numeric_stats:
                st = numeric_stats[q.id]
                item.update(st)
                item['total_responses'] = st['count']
                
                raw_dist = numeric_dist.get(q.id, [])
                dist_sorted = sorted(raw_dist, key=lambda x: x['value'])
                
                item['chart'] = {
                    'labels': [str(int(d['value'])) for d in dist_sorted],
                    'data': [d['count'] for d in dist_sorted],
                    'type': 'bar'
                }
                
                narrative, mood = MetricNarrative.analyze(st, raw_dist, st['max'], q.id)
                trend_val = trend_stats.get(q.id, st['avg'])
                delta = ((trend_val - st['avg']) / st['avg']) * 100 if st['avg'] else 0

                item['insight_data'] = {
                    'type': 'numeric',
                    'avg': st['avg'],
                    'max': st['max'],
                    'trend_delta': delta * 100,
                    'narrative': narrative,
                    'mood': mood
                }
                satisfaction_scores.append(st['avg'])

            # --- Categórico ---
            elif q.id in choice_dist:
                raw_dist = choice_dist[q.id]
                dist_sorted = sorted(raw_dist, key=lambda x: x['count'], reverse=True)
                total_q = sum(d['count'] for d in dist_sorted)
                item['total_responses'] = total_q
                
                top_n = dist_sorted[:8]
                item['chart'] = {
                    'labels': [d['option'] for d in top_n],
                    'data': [d['count'] for d in top_n],
                    'type': 'single'
                }
                
                # Pasamos el objeto 'q' completo para la detección contextual
                narrative = DemographicNarrative.analyze(dist_sorted, total_q, q, q.id)
                
                item['insight_data'] = {
                    'type': 'categorical',
                    'top_option': dist_sorted[0] if dist_sorted else None,
                    'distribution': dist_sorted,
                    'narrative': narrative,
                    'total': total_q
                }

            # --- Texto ---
            elif q.id in text_responses:
                texts = text_responses[q.id]
                clean = SensitiveDataFilter.sanitize_text_responses(texts)
                item['total_responses'] = len(clean)
                item['samples'] = clean[:8]
                
                topics = TextMiningEngine.extract_topics(clean)
                if topics:
                    narrative = f"El análisis semántico ha detectado {len(topics)} conceptos recurrentes: {', '.join(topics[:3])}. Estos temas dominan la conversación en {len(clean)} comentarios analizados."
                else:
                    narrative = "Las respuestas son muy diversas y dispersas, sin patrones lingüísticos claros que indiquen una tendencia unificada."
                
                item['insight_data'] = {
                    'type': 'text',
                    'topics': topics,
                    'narrative': narrative
                }

            analysis_data.append(item)

        kpi_score = (sum(satisfaction_scores)/len(satisfaction_scores)) if satisfaction_scores else 0
        evolution = TimelineEngine.analyze_evolution(survey, responses_queryset, questions)

        result = {
            'analysis_data': analysis_data,
            'kpi_score': kpi_score,
            'evolution': evolution,
            'ignored_questions': skipped_log
        }
        cache.set(cache_key, result, CACHE_TIMEOUT_ANALYSIS)
        return result

    @staticmethod
    def _build_empty_response(skipped):
        return {
            'analysis_data': [], 'kpi_score': 0,
            'evolution': {'labels': [], 'data': [], 'source': 'NONE'},
            'ignored_questions': skipped,
        }

    # --- SQL HELPERS ---
    @staticmethod
    def _fetch_numeric_stats(analyzable_q, qs):
        ids = [q.id for q in analyzable_q if q.type in ['scale', 'number']]
        if not ids: return {}, {}, {}
        
        query = qs.values('id').query
        sql, params = query.get_compiler(using=qs.db).as_sql()
        base_where = f" AND survey_response_id IN ({sql})"
        placeholders = ','.join(['%s'] * len(ids))
        
        stats = {}; dist = defaultdict(list); trend = {}
        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT question_id, COUNT(*), AVG(numeric_value), MAX(numeric_value) 
                FROM surveys_questionresponse WHERE question_id IN ({placeholders}) AND numeric_value IS NOT NULL {base_where} GROUP BY question_id
            """, ids + list(params))
            for r in cursor.fetchall(): stats[r[0]] = {'count': r[1], 'avg': r[2], 'max': r[3]}

            cursor.execute(f"""
                SELECT question_id, numeric_value, COUNT(*) 
                FROM surveys_questionresponse WHERE question_id IN ({placeholders}) AND numeric_value IS NOT NULL {base_where} GROUP BY question_id, numeric_value
            """, ids + list(params))
            for r in cursor.fetchall(): dist[r[0]].append({'value': r[1], 'count': r[2]})
        return stats, dist, trend

    @staticmethod
    def _fetch_choice_stats(analyzable_q, qs):
        ids = [q.id for q in analyzable_q if q.type in ['single', 'multi']]
        if not ids: return {}
        dist = defaultdict(list)
        query = qs.values('id').query
        sql, params = query.get_compiler(using=qs.db).as_sql()
        base_where = f" AND qr.survey_response_id IN ({sql})"
        placeholders = ','.join(['%s'] * len(ids))
        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT qr.question_id, ao.text, COUNT(*) FROM surveys_questionresponse qr JOIN surveys_answeroption ao ON qr.selected_option_id = ao.id WHERE qr.question_id IN ({placeholders}) {base_where} GROUP BY qr.question_id, ao.text
            """, ids + list(params))
            for r in cursor.fetchall(): dist[r[0]].append({'option': r[1], 'count': r[2]})
        return dist

    @staticmethod
    def _fetch_text_responses(analyzable_q, qs):
        ids = [q.id for q in analyzable_q if q.type == 'text']
        if not ids: return {}
        res = defaultdict(list)
        query = qs.values('id').query
        sql, params = query.get_compiler(using=qs.db).as_sql()
        base_where = f" AND survey_response_id IN ({sql})"
        placeholders = ','.join(['%s'] * len(ids))
        with connection.cursor() as cursor:
            cursor.execute(f"""
                SELECT question_id, text_value FROM surveys_questionresponse WHERE question_id IN ({placeholders}) AND text_value <> '' {base_where}
            """, ids + list(params))
            seen = defaultdict(int)
            for r in cursor.fetchall():
                if seen[r[0]] < 150: res[r[0]].append(r[1]); seen[r[0]] += 1
        return res