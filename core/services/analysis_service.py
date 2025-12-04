"""
Service for survey data analysis.
Contains all processing logic and advanced statistical analysis with natural narrative generation.
"""
import re
import collections
import statistics
import pandas as pd
import unicodedata
import math
from django.db.models import Count, Avg
from surveys.models import QuestionResponse
from core.utils.charts import ChartGenerator


def normalize_text(text):
    """Normalización agresiva para análisis semántico."""
    if not text: return ''
    text_str = str(text)
    text_str = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text_str)
    text_str = re.sub(r'[_\-\.\[\]\(\)\{\}:]', ' ', text_str)
    text_str = text_str.replace('¿', '').replace('?', '').replace('¡', '').replace('!', '')
    normalized = unicodedata.normalize('NFKD', text_str).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', normalized).strip().lower()


class ContextHelper:
    """Helper to determine the semantic context of the survey."""
    @staticmethod
    def get_subject_label(category):
        cat = (category or "").lower()
        if any(x in cat for x in ['salud', 'hospital', 'clínica']): return "pacientes"
        if any(x in cat for x in ['educación', 'universidad']): return "estudiantes"
        if any(x in cat for x in ['rrhh', 'empleado', 'laboral']): return "colaboradores"
        if any(x in cat for x in ['hotel', 'turismo']): return "huespedes"
        if any(x in cat for x in ['venta', 'retail']): return "clientes"
        return "encuestados"


class TextAnalyzer:
    """Text analyzer for open-ended responses."""
    SPANISH_STOPWORDS = {
        'de', 'la', 'que', 'el', 'en', 'y', 'a', 'los', 'se', 'del', 'las', 
        'un', 'por', 'con', 'no', 'una', 'su', 'para', 'es', 'al', 'lo', 
        'como', 'mas', 'o', 'sin', 'sobre', 'me', 'mi', 'yo', 'tu', 'te',
        'le', 'si', 'ya', 'ni', 'mismo', 'esta', 'este', 'ese', 'algo',
        'donde', 'cual', 'quien', 'cuando', 'hay', 'ser', 'estar', 'tener',
        'hacer', 'poder', 'dar', 'cada', 'otro', 'tal', 'pero', 'mas', 'muy',
        'son', 'fue', 'era', 'todo', 'nada', 'porque', 'pues'
    }
    POSITIVE_WORDS = {'bien', 'bueno', 'excelente', 'genial', 'mejor', 'feliz', 'satisfecho', 'gracias', 'encanta'}
    NEGATIVE_WORDS = {'mal', 'malo', 'pésimo', 'peor', 'horrible', 'lento', 'difícil', 'error', 'problema', 'queja'}
    
    @staticmethod
    def analyze_sentiment(words):
        pos_count = sum(1 for w in words if w in TextAnalyzer.POSITIVE_WORDS)
        neg_count = sum(1 for w in words if w in TextAnalyzer.NEGATIVE_WORDS)
        total = pos_count + neg_count
        if total == 0: return "Neutral", "bi-chat-square-text", "secondary", "Tono neutral o informativo."
        score = (pos_count - neg_count) / total
        if score > 0.2: return "Positivo", "bi-emoji-smile-fill", "success", "Predominan opiniones favorables."
        elif score < -0.2: return "Negativo", "bi-emoji-frown-fill", "danger", "Se detectan quejas o insatisfacción."
        else: return "Mixto", "bi-emoji-neutral-fill", "warning", "Opiniones balanceadas."

    @staticmethod
    def analyze_text_responses(queryset, max_texts=2000):
        texts = list(queryset.values_list('text_value', flat=True))
        texts = [t for t in texts if t and len(str(t).strip()) > 0]
        if not texts: return [], [], None
        if len(texts) > max_texts: texts = texts[:max_texts]
        text_full = " ".join(str(t) for t in texts).lower()
        clean = re.sub(r'[^\wáéíóúüñ\s]', ' ', text_full)
        words = [w for w in clean.split() if w not in TextAnalyzer.SPANISH_STOPWORDS and len(w) >= 3]
        if not words: return [], [], None
        sentiment_data = TextAnalyzer.analyze_sentiment(words)
        return collections.Counter(words).most_common(5), [], {'label': sentiment_data[0], 'icon': sentiment_data[1], 'color': sentiment_data[2], 'description': sentiment_data[3]}


class QuestionAnalyzer:
    """Specific analyzer per question type with advanced context logic."""

    @staticmethod
    def analyze_numeric_question(question, responses_queryset, include_charts=True):
        question_responses = QuestionResponse.objects.filter(
            question=question,
            survey_response__in=responses_queryset
        )
        values_list = list(question_responses.filter(numeric_value__isnull=False).values_list('numeric_value', flat=True))

        result = {
            'total_respuestas': len(values_list),
            'estadisticas': None, 'avg': None, 'scale_cap': None, 'chart_image': None, 'chart_data': None, 'insight': ''
        }

        if not values_list:
            result['insight'] = "Sin datos numéricos suficientes."
            return result

        val_avg = sum(values_list) / len(values_list)
        val_max = max(values_list)
        result['avg'] = val_avg
        result['estadisticas'] = {
            'minimo': min(values_list), 'maximo': val_max, 'promedio': val_avg, 'mediana': statistics.median(values_list)
        }

        # Detección de Intención
        text_normalized = normalize_text(question.text)
        negative_metrics = ['tiempo', 'espera', 'demora', 'tardanza', 'errores', 'fallos', 'problemas', 'quejas', 'costo']
        demographic_numeric = ['edad', 'años', 'antigüedad', 'hijos', 'personas', 'veces', 'cantidad', 'ingresos', 'salario']
        demographic_categorical = ['area', 'departamento', 'department', 'zona', 'zone', 'sucursal', 'branch', 'codigo', 'code', 'id', 'zip', 'postal', 'year', 'anio']

        intent = "satisfaction"
        if any(k in text_normalized for k in demographic_categorical):
            intent = "demographic_categorical"
        elif any(k in text_normalized for k in demographic_numeric):
            intent = "demographic_numeric"
        elif any(k in text_normalized for k in negative_metrics):
            intent = "negative_metric"

        scale_cap = 5 if val_max <= 5 else (10 if val_max <= 10 else int(val_max))
        result['scale_cap'] = scale_cap

        # Análisis de Dispersión (Standard Deviation)
        stdev = statistics.stdev(values_list) if len(values_list) > 1 else 0
        pattern_text = ""
        if intent in ['satisfaction', 'negative_metric']:
            if stdev < (scale_cap * 0.15):
                pattern_text = "Existe un <strong>fuerte consenso</strong> en las respuestas."
            elif stdev > (scale_cap * 0.25):
                pattern_text = "Las opiniones están <strong>muy divididas (polarización)</strong>."
            else:
                pattern_text = "La dispersión de opiniones es normal."

        # Insight Narrativo
        if intent == "demographic_categorical":
            try:
                mode_val = statistics.mode(values_list)
                mode_count = values_list.count(mode_val)
                pct = round((mode_count / len(values_list)) * 100, 1)
                result['insight'] = f"📊 <strong>Distribución de Categorías</strong>: El código más frecuente es {int(mode_val)} ({pct}%)."
            except:
                result['insight'] = "📊 <strong>Distribución Dispersa</strong>: No hay un valor único predominante."

        elif intent == "demographic_numeric":
            result['insight'] = f"📊 <strong>Perfil Numérico</strong>: Promedio {val_avg:.1f}. {pattern_text}"

        elif intent == "negative_metric":
            norm = (val_avg / scale_cap) * 10 if scale_cap > 0 else 0
            if norm <= 3: mood = "Excelente (Bajo)"
            elif norm <= 6: mood = "Aceptable"
            else: mood = "Crítico (Alto)"
            result['insight'] = f"⏱️ <strong>{mood}</strong>: Promedio {val_avg:.1f}. {pattern_text}"

        else: # Satisfaction
            normalized = (val_avg / scale_cap) * 10 if scale_cap > 0 else 0
            if normalized >= 9.0: mood, icon = "Excelente", "🌟"
            elif normalized >= 7.5: mood, icon = "Bueno", "✅"
            elif normalized >= 6.0: mood, icon = "Regular", "⚠️"
            else: mood, icon = "Crítico", "🛑"
            
            result['insight'] = (
                f"{icon} <strong>{mood}</strong>: Promedio <strong>{val_avg:.1f}</strong> sobre {scale_cap}. "
                f"{pattern_text} Refleja el sentir general de los encuestados."
            )

        if include_charts:
            counts = collections.Counter(values_list)
            sorted_keys = sorted(counts.keys())
            labels = [str(k) for k in sorted_keys]
            data = [counts[k] for k in sorted_keys]
            result['chart_data'] = {'labels': labels, 'data': data}
            
        return result

class DataFrameBuilder:
    @staticmethod
    def build_responses_dataframe(survey, responses_queryset):
        try:
            data = QuestionResponse.objects.filter(survey_response__in=responses_queryset).values(
                'survey_response__id', 'question__text', 'text_value', 'numeric_value', 'selected_option__text'
            )
            df = pd.DataFrame(list(data))
            if df.empty: return pd.DataFrame()
            df['val'] = df['numeric_value'].combine_first(df['selected_option__text']).combine_first(df['text_value'])
            return df.pivot_table(index='survey_response__id', columns='question__text', values='val', aggfunc='first')
        except:
            return pd.DataFrame()

class NPSCalculator:
    @staticmethod
    def calculate_nps(scale_question, responses_queryset, include_chart=True):
        return {'score': 0, 'insight': 'Calculado en dashboard'}