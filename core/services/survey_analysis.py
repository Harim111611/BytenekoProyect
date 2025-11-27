"""
Service to generate complete survey analysis data.
Combines all analyzers to create reports.
"""
from django.db.models import Avg
from django.core.cache import cache

from surveys.models import QuestionResponse
from core.services.analysis_service import (
    QuestionAnalyzer, NPSCalculator, DataFrameBuilder
)
from core.utils.charts import ChartGenerator
from core.utils.logging_utils import log_performance, log_query_count


class SurveyAnalysisService:
    """Main service for complete survey analysis."""
    
    @staticmethod
    @log_performance(threshold_ms=2000)
    @log_query_count
    def get_analysis_data(survey, responses_queryset, include_charts=True, cache_key=None):
        """
        Generates complete analysis data for a survey.
        """
        if cache_key:
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data
        
        analysis_data = []
        questions = survey.questions.prefetch_related('options').order_by('order')
        
        satisfaction_avg = 0
        scale_questions = questions.filter(type='scale')
        if scale_questions.exists():
            vals = QuestionResponse.objects.filter(
                question__in=scale_questions,
                survey_response__in=responses_queryset,
                numeric_value__isnull=False
            ).aggregate(avg=Avg('numeric_value'))
            satisfaction_avg = vals['avg'] or 0
        
        nps_question = scale_questions.first()
        nps_data = NPSCalculator.calculate_nps(
            nps_question, responses_queryset, include_chart=include_charts
        )
        
        heatmap_image = None
        if include_charts:
            try:
                df = DataFrameBuilder.build_responses_dataframe(survey, responses_queryset)
                if not df.empty:
                    heatmap_image = ChartGenerator.generate_heatmap(df)
            except Exception:
                pass
        
        for i, question in enumerate(questions, 1):
            item = {
                'id': question.id, 'order': i, 'text': question.text, 'type': question.type,
                'tipo_display': question.get_type_display(), # Standard
                'insight': '', 'chart_image': None, 'chart_data': None,
                'total_respuestas': 0, 'estadisticas': None, 'opciones': [],
                'samples_texto': [], 'top_options': [], 'avg': None, 'scale_cap': None,
            }
            
            if question.type in ['number', 'scale']:
                result = QuestionAnalyzer.analyze_numeric_question(
                    question, responses_queryset, include_charts
                )
                item.update(result)
                
                # --- VISUAL TAG CORRECTION ---
                if result.get('scale_cap') == 5:
                    item['tipo_display'] = 'Escala 1-5'
                elif result.get('scale_cap') and result.get('scale_cap') > 10:
                    item['tipo_display'] = 'Valor Numérico'
                # -----------------------------
                
            elif question.type in ['single', 'multi']:
                result = QuestionAnalyzer.analyze_choice_question(
                    question, responses_queryset, include_charts
                )
                item.update(result)
                
            elif question.type == 'text':
                result = QuestionAnalyzer.analyze_text_question(
                    question, responses_queryset
                )
                item.update(result)
            
            analysis_data.append(item)
        
        final_data = {
            'analysis_data': analysis_data,
            'nps_data': nps_data,
            'heatmap_image': heatmap_image,
            'kpi_prom_satisfaccion': satisfaction_avg,
        }
        
        if cache_key:
            cache.set(cache_key, final_data, 3600)
        
        return final_data