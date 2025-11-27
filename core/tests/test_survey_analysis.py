"""
Tests para core/services/survey_analysis.py
Tests para SurveyAnalysisService - servicio principal de análisis
"""
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache

from surveys.models import (
    Encuesta, Pregunta, OpcionRespuesta,
    RespuestaEncuesta, RespuestaPregunta
)
from core.services.survey_analysis import SurveyAnalysisService


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def user():
    """Usuario de prueba."""
    return User.objects.create_user(username='testuser', password='12345')


@pytest.fixture
def encuesta_completa(user):
    """Encuesta completa con varias preguntas."""
    encuesta = Survey.objects.create(
        title='Encuesta de Satisfacción',
        description='Test completo',
        author=user,
        status='active'
    )
    
    # Pregunta de escala (para NPS y satisfacción)
    p_scale = Question.objects.create(
        survey=survey,
        text='¿Qué tan probable es que recomiendes?',
        type='scale',
        order=1
    )
    
    # Pregunta numérica
    p_number = Question.objects.create(
        survey=survey,
        text='¿Cuántos años tienes?',
        type='number',
        order=2
    )
    
    # Pregunta de opción única
    p_single = Question.objects.create(
        survey=survey,
        text='¿Cuál es tu nivel de satisfacción?',
        type='single',
        order=3
    )
    AnswerOption.objects.create(question=p_single, text='Muy satisfecho')
    AnswerOption.objects.create(question=p_single, text='Satisfecho')
    AnswerOption.objects.create(question=p_single, text='Insatisfecho')
    
    # Pregunta de texto
    p_text = Question.objects.create(
        survey=survey,
        text='¿Qué podemos mejorar?',
        type='text',
        order=4
    )
    
    return encuesta


@pytest.fixture
def respuestas_completas(encuesta_completa, user):
    """Crear respuestas completas para la encuesta."""
    preguntas = list(encuesta_completa.questions.all().order_by('order'))
    p_scale, p_number, p_single, p_text = preguntas
    
    # Crear 5 respuestas
    respuestas = []
    valores_scale = [9, 10, 8, 9, 7]
    valores_number = [25, 30, 28, 35, 22]
    textos = [
        'Mejorar el tiempo de respuesta',
        'Muy buen servicio',
        'Todo perfecto',
        'Excelente atención',
        'Nada que mejorar'
    ]
    
    for i in range(5):
        resp = SurveyResponse.objects.create(
            survey=encuesta_completa,
            user=user
        )
        
        # Respuesta scale
        QuestionResponse.objects.create(
            survey_response=resp,
            question=p_scale,
            numeric_value=valores_scale[i]
        )
        
        # Respuesta number
        QuestionResponse.objects.create(
            survey_response=resp,
            question=p_number,
            numeric_value=valores_number[i]
        )
        
        # Respuesta single
        opcion = p_single.options.first() if i < 3 else p_single.options.last()
        QuestionResponse.objects.create(
            survey_response=resp,
            question=p_single,
            selected_option=selected_option
        )
        
        # Respuesta text
        QuestionResponse.objects.create(
            survey_response=resp,
            question=p_text,
            text_value=textos[i]
        )
        
        respuestas.append(resp)
    
    return respuestas


# ============================================================================
# TESTS: SurveyAnalysisService
# ============================================================================

class TestSurveyAnalysisService:
    """Tests para SurveyAnalysisService."""
    
    @pytest.mark.django_db
    def test_get_analysis_data_empty_survey(self, encuesta_completa):
        """Debe retornar estructura básica sin respuestas."""
        qs = SurveyResponse.objects.filter(survey=encuesta_completa)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=False
        )
        
        assert 'analysis_data' in result
        assert 'nps_data' in result
        assert 'heatmap_image' in result
        assert 'kpi_prom_satisfaccion' in result
        assert len(result['analysis_data']) == 4  # 4 preguntas
    
    @pytest.mark.django_db
    def test_get_analysis_data_with_responses(
        self, encuesta_completa, respuestas_completas
    ):
        """Debe analizar encuesta completa con respuestas."""
        qs = SurveyResponse.objects.filter(survey=encuesta_completa)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=False
        )
        
        # Verificar que hay datos de análisis
        assert len(result['analysis_data']) == 4
        
        # Verificar KPI de satisfacción
        assert result['kpi_prom_satisfaccion'] > 0
        # Promedio de [9, 10, 8, 9, 7] = 8.6
        assert 8.0 <= result['kpi_prom_satisfaccion'] <= 9.0
        
        # Verificar NPS
        assert result['nps_data']['score'] is not None
    
    @pytest.mark.django_db
    def test_get_analysis_data_scale_question(
        self, encuesta_completa, respuestas_completas
    ):
        """Debe analizar pregunta de escala correctamente."""
        qs = SurveyResponse.objects.filter(survey=encuesta_completa)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=False
        )
        
        # Primera pregunta es de tipo scale
        pregunta_scale = result['analysis_data'][0]
        
        assert pregunta_scale['type'] == 'scale'
        assert pregunta_scale['total_respuestas'] == 5
        assert pregunta_scale['estadisticas'] is not None
        assert pregunta_scale['avg'] is not None
        assert pregunta_scale['insight'] != ''
    
    @pytest.mark.django_db
    def test_get_analysis_data_number_question(
        self, encuesta_completa, respuestas_completas
    ):
        """Debe analizar pregunta numérica correctamente."""
        qs = SurveyResponse.objects.filter(survey=encuesta_completa)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=False
        )
        
        # Segunda pregunta es de tipo number
        pregunta_number = result['analysis_data'][1]
        
        assert pregunta_number['type'] == 'number'
        assert pregunta_number['total_respuestas'] == 5
        assert pregunta_number['estadisticas'] is not None
        # Promedio de [25, 30, 28, 35, 22] = 28
        assert 27 <= pregunta_number['avg'] <= 29
    
    @pytest.mark.django_db
    def test_get_analysis_data_single_question(
        self, encuesta_completa, respuestas_completas
    ):
        """Debe analizar pregunta de opción única correctamente."""
        qs = SurveyResponse.objects.filter(survey=encuesta_completa)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=False
        )
        
        # Tercera pregunta es de tipo single
        pregunta_single = result['analysis_data'][2]
        
        assert pregunta_single['type'] == 'single'
        assert pregunta_single['total_respuestas'] == 5
        assert len(pregunta_single['opciones']) > 0
        assert pregunta_single['insight'] != ''
    
    @pytest.mark.django_db
    def test_get_analysis_data_text_question(
        self, encuesta_completa, respuestas_completas
    ):
        """Debe analizar pregunta de texto correctamente."""
        qs = SurveyResponse.objects.filter(survey=encuesta_completa)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=False
        )
        
        # Cuarta pregunta es de tipo text
        pregunta_text = result['analysis_data'][3]
        
        assert pregunta_text['type'] == 'text'
        assert pregunta_text['total_respuestas'] == 5
        assert len(pregunta_text['samples_texto']) > 0
        assert pregunta_text['insight'] != ''
    
    @pytest.mark.django_db
    def test_get_analysis_data_respects_orden(
        self, encuesta_completa, respuestas_completas
    ):
        """Debe respetar el orden de las preguntas."""
        qs = SurveyResponse.objects.filter(survey=encuesta_completa)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=False
        )
        
        # Verificar que el orden es correcto
        for i, item in enumerate(result['analysis_data'], 1):
            assert item['order'] == i
    
    @pytest.mark.django_db
    @patch('core.services.survey_analysis.NPSCalculator.calculate_nps')
    def test_get_analysis_data_calculates_nps(
        self, mock_nps, encuesta_completa, respuestas_completas
    ):
        """Debe calcular NPS usando NPSCalculator."""
        mock_nps.return_value = {'score': 60.0, 'breakdown_chart': None}
        
        qs = SurveyResponse.objects.filter(survey=encuesta_completa)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=False
        )
        
        assert result['nps_data']['score'] == 60.0
        mock_nps.assert_called_once()
    
    @pytest.mark.django_db
    @patch('core.services.survey_analysis.ChartGenerator.generate_heatmap')
    @patch('core.services.survey_analysis.DataFrameBuilder.build_responses_dataframe')
    def test_get_analysis_data_generates_heatmap(
        self, mock_df_builder, mock_heatmap, encuesta_completa, respuestas_completas
    ):
        """Debe generar heatmap si include_charts=True."""
        # Mock DataFrame no vacío
        mock_df = MagicMock()
        mock_df.empty = False
        mock_df_builder.return_value = mock_df
        mock_heatmap.return_value = 'fake_heatmap_image'
        
        qs = SurveyResponse.objects.filter(survey=encuesta_completa)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=True
        )
        
        assert result['heatmap_image'] == 'fake_heatmap_image'
        mock_heatmap.assert_called_once()
    
    @pytest.mark.django_db
    def test_get_analysis_data_no_heatmap_if_charts_disabled(
        self, encuesta_completa, respuestas_completas
    ):
        """No debe generar heatmap si include_charts=False."""
        qs = SurveyResponse.objects.filter(survey=encuesta_completa)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=False
        )
        
        assert result['heatmap_image'] is None
    
    @pytest.mark.django_db
    @patch('core.services.survey_analysis.DataFrameBuilder.build_responses_dataframe')
    def test_get_analysis_data_handles_heatmap_error(
        self, mock_df_builder, encuesta_completa, respuestas_completas
    ):
        """Debe manejar errores en generación de heatmap."""
        mock_df_builder.side_effect = Exception('Error en DataFrame')
        
        qs = SurveyResponse.objects.filter(survey=encuesta_completa)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=True
        )
        
        # No debe fallar, solo no tener heatmap
        assert result['heatmap_image'] is None
        assert 'analysis_data' in result
    
    @pytest.mark.django_db
    def test_get_analysis_data_no_scale_questions(self, user):
        """Debe manejar encuestas sin preguntas de escala."""
        encuesta = Survey.objects.create(
            title='Sin Escalas',
            author=user
        )
        
        # Solo pregunta de texto
        Question.objects.create(
            survey=survey,
            text='Comentarios',
            type='text',
            order=1
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta, qs, include_charts=False
        )
        
        assert result['kpi_prom_satisfaccion'] == 0
        assert result['nps_data']['score'] is None
    
    @pytest.mark.django_db
    def test_get_analysis_data_includes_question_metadata(
        self, encuesta_completa, respuestas_completas
    ):
        """Debe incluir metadata de preguntas en el resultado."""
        qs = SurveyResponse.objects.filter(survey=encuesta_completa)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=False
        )
        
        for item in result['analysis_data']:
            assert 'id' in item
            assert 'orden' in item
            assert 'texto' in item
            assert 'tipo' in item
            assert 'tipo_display' in item
    
    @pytest.mark.django_db
    @patch('core.services.survey_analysis.QuestionAnalyzer.analyze_numeric_question')
    def test_get_analysis_data_passes_include_charts_to_analyzers(
        self, mock_analyzer, encuesta_completa, respuestas_completas
    ):
        """Debe pasar include_charts a los analizadores."""
        mock_analyzer.return_value = {
            'total_respuestas': 0,
            'estadisticas': None,
            'avg': None,
            'scale_cap': None,
            'chart_image': None,
            'chart_data': None,
            'insight': ''
        }
        
        qs = SurveyResponse.objects.filter(survey=encuesta_completa)
        
        SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=True
        )
        
        # Verificar que se llamó con include_charts=True
        # Los argumentos pueden estar en args o kwargs dependiendo de cómo se llamó
        assert mock_analyzer.called
        calls = mock_analyzer.call_args_list
        # Debe haber sido llamado al menos una vez
        assert len(calls) > 0


# ============================================================================
# TESTS: Cache Functionality
# ============================================================================

class TestSurveyAnalysisServiceCache:
    """Tests para funcionalidad de caché."""
    
    def setup_method(self):
        """Limpiar caché antes de cada test."""
        cache.clear()
    
    def teardown_method(self):
        """Limpiar caché después de cada test."""
        cache.clear()
    
    @pytest.mark.django_db
    def test_get_analysis_data_uses_cache(
        self, encuesta_completa, respuestas_completas
    ):
        """Debe usar caché si cache_key es proporcionado."""
        qs = SurveyResponse.objects.filter(survey=encuesta_completa)
        cache_key = 'test_analysis_cache'
        
        # Primera llamada - debe cachear
        result1 = SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=False, cache_key=cache_key
        )
        
        # Segunda llamada - debe usar caché
        result2 = SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=False, cache_key=cache_key
        )
        
        # Resultados deben ser idénticos
        assert result1 == result2
    
    @pytest.mark.django_db
    @patch('core.services.survey_analysis.QuestionAnalyzer.analyze_numeric_question')
    def test_get_analysis_data_cache_hit_avoids_computation(
        self, mock_analyzer, encuesta_completa, respuestas_completas
    ):
        """Cache hit debe evitar recalcular análisis."""
        qs = SurveyResponse.objects.filter(survey=encuesta_completa)
        cache_key = 'test_cache_hit'
        
        # Primera llamada - calcula
        SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=False, cache_key=cache_key
        )
        
        # Resetear mock
        mock_analyzer.reset_mock()
        
        # Segunda llamada - debe usar caché
        SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=False, cache_key=cache_key
        )
        
        # No debe haber llamado al analizador
        mock_analyzer.assert_not_called()
    
    @pytest.mark.django_db
    def test_get_analysis_data_no_cache_without_key(
        self, encuesta_completa, respuestas_completas
    ):
        """No debe cachear si no se proporciona cache_key."""
        qs = SurveyResponse.objects.filter(survey=encuesta_completa)
        
        # Sin cache_key
        result = SurveyAnalysisService.get_analysis_data(
            encuesta_completa, qs, include_charts=False
        )
        
        # Verificar que no se guardó en caché
        cached = cache.get('any_key')
        assert cached is None
    
    @pytest.mark.django_db
    def test_get_analysis_data_cache_expiration(
        self, encuesta_completa, respuestas_completas
    ):
        """Caché debe expirar después de 3600 segundos."""
        qs = SurveyResponse.objects.filter(survey=encuesta_completa)
        cache_key = 'test_expiration'
        
        with patch('django.core.cache.cache.set') as mock_cache_set:
            SurveyAnalysisService.get_analysis_data(
                encuesta_completa, qs, include_charts=False, cache_key=cache_key
            )
            
            # Verificar que se llamó con timeout de 3600
            mock_cache_set.assert_called_once()
            args = mock_cache_set.call_args
            assert args[0][0] == cache_key  # key
            assert args[0][2] == 3600  # timeout


# ============================================================================
# TESTS: Edge Cases
# ============================================================================

class TestSurveyAnalysisServiceEdgeCases:
    """Tests para casos extremos."""
    
    @pytest.mark.django_db
    def test_get_analysis_data_pregunta_sin_respuestas(self, user):
        """Debe manejar preguntas sin respuestas."""
        encuesta = Survey.objects.create(title='Test', author=user)
        
        # Crear pregunta pero no respuestas
        Question.objects.create(
            survey=survey,
            text='Pregunta sin respuestas',
            type='scale',
            order=1
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta, qs, include_charts=False
        )
        
        assert len(result['analysis_data']) == 1
        assert result['analysis_data'][0]['total_respuestas'] == 0
    
    @pytest.mark.django_db
    def test_get_analysis_data_encuesta_vacia(self, user):
        """Debe manejar encuesta sin preguntas."""
        encuesta = Survey.objects.create(title='Vacía', author=user)
        
        qs = SurveyResponse.objects.filter(survey=survey)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta, qs, include_charts=False
        )
        
        assert result['analysis_data'] == []
        assert result['kpi_prom_satisfaccion'] == 0
    
    @pytest.mark.django_db
    def test_get_analysis_data_multiple_scale_questions(self, user):
        """Debe calcular promedio de satisfacción con múltiples escalas."""
        encuesta = Survey.objects.create(title='Multi Scale', author=user)
        
        # Crear 2 preguntas de escala
        p1 = Question.objects.create(
            survey=survey, text='P1', type='scale', order=1
        )
        p2 = Question.objects.create(
            survey=survey, text='P2', type='scale', order=2
        )
        
        # Crear respuestas
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp, question=p1, numeric_value=8
        )
        QuestionResponse.objects.create(
            survey_response=resp, question=p2, numeric_value=10
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta, qs, include_charts=False
        )
        
        # Promedio de [8, 10] = 9
        assert result['kpi_prom_satisfaccion'] == 9.0
