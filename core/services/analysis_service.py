"""
Service for survey data analysis.
Contains all processing logic and advanced statistical analysis with natural narrative generation.
Optimized for Database Aggregations over Python iterables to handle large datasets efficiently.
"""
import re
import collections
import statistics
import pandas as pd
import unicodedata
import math
import logging
from django.db.models import Count, Avg, Min, Max, StdDev
from surveys.models import QuestionResponse
# Asumimos que ChartGenerator existe en utils, si no, se maneja el error gracefully
try:
    from core.utils.charts import ChartGenerator
except ImportError:
    ChartGenerator = None

logger = logging.getLogger(__name__)

def normalize_text(text):
    """Normalización agresiva para análisis semántico."""
    if not text: return ''
    text_str = str(text)
    # Separar CamelCase
    text_str = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text_str)
    # Reemplazar puntuación común
    text_str = re.sub(r'[_\-\.\[\]\(\)\{\}:]', ' ', text_str)
    text_str = text_str.replace('¿', '').replace('?', '').replace('¡', '').replace('!', '')
    # Normalizar caracteres latinos
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
    POSITIVE_WORDS = {'bien', 'bueno', 'excelente', 'genial', 'mejor', 'feliz', 'satisfecho', 'gracias', 'encanta', 'perfecto', 'amable'}
    NEGATIVE_WORDS = {'mal', 'malo', 'pésimo', 'peor', 'horrible', 'lento', 'difícil', 'error', 'problema', 'queja', 'sucio', 'grosero'}
    
    @staticmethod
    def analyze_sentiment(words):
        pos_count = sum(1 for w in words if w in TextAnalyzer.POSITIVE_WORDS)
        neg_count = sum(1 for w in words if w in TextAnalyzer.NEGATIVE_WORDS)
        total = pos_count + neg_count
        
        if total == 0: 
            return "Neutral", "bi-chat-square-text", "secondary", "Tono neutral o informativo."
        
        score = (pos_count - neg_count) / total
        
        if score > 0.2: 
            return "Positivo", "bi-emoji-smile-fill", "success", "Predominan opiniones favorables."
        elif score < -0.2: 
            return "Negativo", "bi-emoji-frown-fill", "danger", "Se detectan quejas o insatisfacción."
        else: 
            return "Mixto", "bi-emoji-neutral-fill", "warning", "Opiniones balanceadas."

    @staticmethod
    def analyze_text_responses(queryset, max_texts=2000):
        # Optimización: values_list con flat=True es más rápido que cargar objetos
        texts = list(queryset.values_list('text_value', flat=True))
        texts = [t for t in texts if t and len(str(t).strip()) > 0]
        
        if not texts: 
            return [], [], None
            
        if len(texts) > max_texts: 
            texts = texts[:max_texts]
            
        text_full = " ".join(str(t) for t in texts).lower()
        # Limpieza básica rápida
        clean = re.sub(r'[^\wáéíóúüñ\s]', ' ', text_full)
        words = [w for w in clean.split() if w not in TextAnalyzer.SPANISH_STOPWORDS and len(w) >= 3]
        
        if not words: 
            return [], [], None
            
        sentiment_data = TextAnalyzer.analyze_sentiment(words)
        top_words = collections.Counter(words).most_common(10)
        
        # Formato de retorno para la vista
        insight_data = {
            'label': sentiment_data[0], 
            'icon': sentiment_data[1], 
            'color': sentiment_data[2], 
            'description': sentiment_data[3]
        }
        
        return top_words, [], insight_data


class QuestionAnalyzer:
    """Specific analyzer per question type with DB optimizations."""

    @staticmethod
    def analyze_numeric_question(question, responses_queryset, include_charts=True):
        # 1. Obtener estadísticas directamente de la DB
        qs = QuestionResponse.objects.filter(
            question=question,
            survey_response__in=responses_queryset,
            numeric_value__isnull=False
        )
        
        aggregates = qs.aggregate(
            avg=Avg('numeric_value'),
            min=Min('numeric_value'),
            max=Max('numeric_value'),
            std_dev=StdDev('numeric_value'),
            count=Count('id')
        )
        
        count = aggregates['count']
        if count == 0:
            return {
                'id': question.id, 'text': question.text, 'type': question.type, 'order': question.order,
                'total_respuestas': 0, 'estadisticas': None, 'avg': None, 
                'insight': "Sin datos numéricos suficientes."
            }

        val_avg = aggregates['avg'] or 0
        val_max = aggregates['max'] or 0
        stdev = aggregates['std_dev'] or 0
        
        # 2. Datos para gráficos (Agrupados por valor en DB)
        chart_data_dict = {'labels': [], 'data': []}
        if include_charts:
            distribution = qs.values('numeric_value').annotate(freq=Count('id')).order_by('numeric_value')
            for entry in distribution:
                chart_data_dict['labels'].append(str(entry['numeric_value']))
                chart_data_dict['data'].append(entry['freq'])

        scale_cap = 5 if val_max <= 5 else (10 if val_max <= 10 else int(val_max))
        
        insight_text = QuestionAnalyzer._generate_numeric_insight(question.text, val_avg, scale_cap, stdev)

        return {
            'id': question.id,
            'text': question.text,
            'type': question.type,
            'order': question.order,
            'total_respuestas': count,
            'avg': val_avg,
            'estadisticas': {
                'minimo': aggregates['min'], 
                'maximo': val_max, 
                'promedio': val_avg,
                'mediana': val_avg # Aproximación para evitar cálculo costoso en Python
            },
            'chart_labels': chart_data_dict['labels'],
            'chart_data': chart_data_dict['data'],
            'insight': insight_text,
            'opciones': [] # Estandarización de estructura
        }
    
    @staticmethod
    def analyze_choice_question(question, responses_queryset, include_charts=True):
        """Analiza preguntas de selección múltiple o única usando agregación DB."""
        qs = QuestionResponse.objects.filter(
            question=question,
            survey_response__in=responses_queryset
        ).exclude(selected_option__isnull=True)
        
        total = qs.count()
        if total == 0:
             return {
                'id': question.id, 'text': question.text, 'type': question.type, 'order': question.order,
                'total_respuestas': 0, 'insight': "Sin respuestas registradas."
            }

        # Agregación por opción seleccionada (Mucho más rápido que iterar)
        distribution = qs.values('selected_option__text').annotate(count=Count('id')).order_by('-count')
        
        labels = []
        data = []
        top_options = []
        
        for item in distribution:
            lbl = item['selected_option__text'] or "Sin etiqueta"
            cnt = item['count']
            labels.append(lbl)
            data.append(cnt)
            top_options.append({'label': lbl, 'count': cnt, 'percent': (cnt/total)*100})
            
        # Generar Insight
        insight = ""
        if top_options:
            top = top_options[0]
            insight = f"La opción predominante fue <strong>{top['label']}</strong> con el {top['percent']:.1f}% de los votos."
            if len(top_options) > 1:
                sec = top_options[1]
                insight += f" Le sigue <strong>{sec['label']}</strong> con {sec['percent']:.1f}%."

        return {
            'id': question.id,
            'text': question.text,
            'type': question.type,
            'order': question.order,
            'total_respuestas': total,
            'chart_labels': labels,
            'chart_data': data,
            'insight': insight,
            'opciones': top_options,
            'top_options': top_options[:3]
        }

    @staticmethod
    def _generate_numeric_insight(text, val_avg, scale_cap, stdev):
        text_normalized = normalize_text(text)
        negative_metrics = ['tiempo', 'espera', 'demora', 'queja', 'retraso']
        
        pattern_text = "Dispersión normal."
        if scale_cap > 0:
            if stdev < (scale_cap * 0.15): pattern_text = "Alto consenso en las respuestas."
            elif stdev > (scale_cap * 0.25): pattern_text = "Opiniones divididas (polarización)."

        if any(x in text_normalized for x in negative_metrics):
             norm = (val_avg / scale_cap) * 10 if scale_cap > 0 else 0
             mood = "Excelente" if norm <= 3 else "Crítico"
             return f"⏱️ <strong>{mood}</strong>: Promedio {val_avg:.1f}. {pattern_text}"
        
        # Satisfacción default
        return f"📊 Promedio: <strong>{val_avg:.1f}</strong>/{scale_cap}. {pattern_text}"


class DataFrameBuilder:
    @staticmethod
    def build_responses_dataframe(survey, responses_queryset):
        # Optimización: Usar iterator si el dataset es muy grande.
        # Obtenemos solo los campos necesarios
        data = list(QuestionResponse.objects.filter(survey_response__in=responses_queryset).values(
            'survey_response__id', 'question__text', 'text_value', 'numeric_value', 'selected_option__text'
        ))
        
        if not data: return pd.DataFrame()
        
        df = pd.DataFrame(data)
        # Coalesce eficiente: Prioridad Numeric > Option > Text
        df['val'] = df['numeric_value'].combine_first(df['selected_option__text']).combine_first(df['text_value'])
        
        if df.empty: return pd.DataFrame()

        # Pivotar: Filas=Respuestas, Columnas=Preguntas
        return df.pivot_table(index='survey_response__id', columns='question__text', values='val', aggfunc='first')


class NPSCalculator:
    @staticmethod
    def calculate_nps(survey, responses_queryset):
        """Intenta calcular NPS si encuentra una pregunta compatible (Escala 0-10)."""
        # Heurística simple para encontrar pregunta NPS
        nps_question = survey.questions.filter(type__in=['scale', 'number'], text__icontains='recomendar').first()
        
        if not nps_question:
            return {'score': None, 'promoters': 0, 'passives': 0, 'detractors': 0, 'chart_image': None}
            
        qs = QuestionResponse.objects.filter(question=nps_question, survey_response__in=responses_queryset, numeric_value__isnull=False)
        total = qs.count()
        if total == 0:
            return {'score': None, 'promoters': 0, 'passives': 0, 'detractors': 0}
            
        promoters = qs.filter(numeric_value__gte=9).count()
        detractors = qs.filter(numeric_value__lte=6).count()
        passives = total - (promoters + detractors)
        
        score = ((promoters - detractors) / total) * 100
        
        # Generar gráfico simple si es posible
        chart_image = None
        if ChartGenerator:
             chart_image = ChartGenerator.generate_donut_chart(
                 ['Promotores', 'Pasivos', 'Detractores'], 
                 [promoters, passives, detractors],
                 ['#10B981', '#6B7280', '#EF4444']
             )

        return {
            'score': round(score, 1),
            'promoters': promoters,
            'passives': passives,
            'detractors': detractors,
            'total': total,
            'chart_image': chart_image
        }


class SurveyAnalysisService:
    """
    Servicio principal de orquestación para el análisis de encuestas.
    Integra todos los analizadores y constructores.
    """
    @staticmethod
    def get_analysis_data(survey, responses_queryset, include_charts=True, cache_key=None, use_base_filter=True):
        """
        Método principal llamado por las vistas.
        Retorna un diccionario completo con datos analizados, KPIs y gráficos.
        """
        # 1. KPIs Globales (NPS)
        nps_data = NPSCalculator.calculate_nps(survey, responses_queryset)
        
        # 2. Análisis por Pregunta
        # Filtramos preguntas analizables (ignoramos descriptivas o saltos de sección si existen)
        questions = survey.questions.all().order_by('order') 
        if hasattr(questions.first(), 'is_analyzable'):
            questions = questions.filter(is_analyzable=True)

        analysis_data = []
        satisfaction_values = []
        
        for question in questions:
            item = None
            
            try:
                if question.type in ['scale', 'number']:
                    item = QuestionAnalyzer.analyze_numeric_question(question, responses_queryset, include_charts)
                    if item.get('avg') is not None:
                        satisfaction_values.append(item['avg'])
                        
                elif question.type in ['single', 'multi']:
                    item = QuestionAnalyzer.analyze_choice_question(question, responses_queryset, include_charts)
                    
                elif question.type == 'text':
                    # Análisis de texto
                    q_res = QuestionResponse.objects.filter(question=question, survey_response__in=responses_queryset)
                    top_words, _, sentiment = TextAnalyzer.analyze_text_responses(q_res)
                    
                    insight = ""
                    if sentiment:
                        insight = f"Sentimiento: {sentiment['label']}. {sentiment['description']}"
                        
                    item = {
                        'id': question.id, 'text': question.text, 'type': question.type, 'order': question.order,
                        'total_respuestas': q_res.count(),
                        'insight': insight,
                        'top_words': top_words,
                        'sentiment': sentiment,
                        'opciones': []
                    }
                else:
                    # Fallback para tipos desconocidos
                    item = {
                        'id': question.id, 'text': question.text, 'type': question.type, 'order': question.order,
                        'total_respuestas': 0, 'insight': ""
                    }
            except Exception as e:
                logger.error(f"Error analizando pregunta {question.id}: {e}")
                item = {'id': question.id, 'text': question.text, 'error': str(e)}

            if item:
                analysis_data.append(item)

        # 3. KPI Promedio Satisfacción General
        kpi_satisfaction = 0
        if satisfaction_values:
            kpi_satisfaction = sum(satisfaction_values) / len(satisfaction_values)

        # 4. Heatmap de Correlaciones (Solo si ChartGenerator está disponible)
        heatmap_image = None
        heatmap_image_dark = None
        if include_charts and ChartGenerator and len(satisfaction_values) > 1:
            try:
                df = DataFrameBuilder.build_responses_dataframe(survey, responses_queryset)
                # Filtrar solo columnas numéricas para correlación
                numeric_df = df.select_dtypes(include=['number'])
                if not numeric_df.empty and numeric_df.shape[1] > 1:
                    heatmap_image = ChartGenerator.generate_heatmap(numeric_df)
                    # Opcional: generar versión dark si el generador lo soporta
            except Exception as e:
                logger.warning(f"No se pudo generar heatmap: {e}")

        return {
            'survey': survey,
            'analysis_data': analysis_data,
            'nps_data': nps_data,
            'kpi_prom_satisfaccion': kpi_satisfaction,
            'heatmap_image': heatmap_image,
            'heatmap_image_dark': heatmap_image_dark,
            'total_responses': responses_queryset.count()
        }