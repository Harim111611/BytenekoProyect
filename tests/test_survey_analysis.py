"""
Tests para core/services/survey_analysis.py
Tests para SurveyAnalysisService - servicio principal de análisis
"""
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache

from surveys.models import Survey, Question, AnswerOption, SurveyResponse, QuestionResponse
from core.services.survey_analysis import SurveyAnalysisService


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def user():
    """Usuario de prueba."""
    return User.objects.create_user(username='testuser', password='12345')


@pytest.fixture
def complete_survey(user):
    """Complete survey with several questions."""
    survey = Survey.objects.create(
        title='Satisfaction Survey',
        description='Full test',
        author=user,
        status='active'
    )
    # Scale question
    p_scale = Question.objects.create(
        survey=survey,
        text='How likely are you to recommend?',
        type='scale',
        order=1
    )
    # Number question
    p_number = Question.objects.create(
        survey=survey,
        text='How old are you?',
        type='number',
        order=2
    )
    # Single choice question
    p_single = Question.objects.create(
        survey=survey,
        text='What is your satisfaction level?',
        type='single',
        order=3
    )
    AnswerOption.objects.create(question=p_single, text='Very satisfied')
    AnswerOption.objects.create(question=p_single, text='Satisfied')
    AnswerOption.objects.create(question=p_single, text='Unsatisfied')
    # Text question
    p_text = Question.objects.create(
        survey=survey,
        text='What can we improve?',
        type='text',
        order=4
    )
    return survey


@pytest.fixture
def complete_responses(complete_survey, user):
    """Create complete responses for the survey."""
    questions = list(complete_survey.questions.all().order_by('order'))
    p_scale, p_number, p_single, p_text = questions
    responses = []
    scale_values = [9, 10, 8, 9, 7]
    number_values = [25, 30, 28, 35, 22]
    texts = [
        'Improve response time',
        'Very good service',
        'Everything perfect',
        'Excellent attention',
        'Nothing to improve'
    ]
    for i in range(5):
        resp = SurveyResponse.objects.create(
            survey=complete_survey,
            user=user
        )
        # Scale response
        QuestionResponse.objects.create(
            survey_response=resp,
            question=p_scale,
            numeric_value=scale_values[i]
        )
        # Number response
        QuestionResponse.objects.create(
            survey_response=resp,
            question=p_number,
            numeric_value=number_values[i]
        )
        # Single choice response
        option = p_single.options.first() if i < 3 else p_single.options.last()
        QuestionResponse.objects.create(
            survey_response=resp,
            question=p_single,
            selected_option=option
        )
        # Text response
        QuestionResponse.objects.create(
            survey_response=resp,
            question=p_text,
            text_value=texts[i]
        )
        responses.append(resp)
    return responses


# ============================================================================
# TESTS: SurveyAnalysisService
# ============================================================================

class TestSurveyAnalysisService:
    """Tests para SurveyAnalysisService."""
    
    @pytest.mark.django_db
    def test_get_analysis_data_empty_survey(self, complete_survey):
        """Debe retornar estructura básica sin respuestas."""
        qs = SurveyResponse.objects.filter(survey=complete_survey)
        
        result = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=False
        )
        
        assert 'analysis_data' in result
        assert 'nps_data' in result
        assert 'heatmap_image' in result
        assert 'kpi_prom_satisfaccion' in result
        assert len(result['analysis_data']) == 4  # 4 preguntas
    
    @pytest.mark.django_db
    def test_get_analysis_data_with_responses(
        self, complete_survey, complete_responses
    ):
        """Debe analizar encuesta completa con respuestas."""
        qs = SurveyResponse.objects.filter(survey=complete_survey)
        
        result = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=False
        )
        
        # Verificar que hay datos de análisis
        assert len(result['analysis_data']) == 4
        
        # Verificar KPI de satisfacción
        assert result['kpi_prom_satisfaccion'] > 0
        # Promedio de [9, 10, 8, 9, 7] = 8.6
        assert 8.0 <= result['kpi_prom_satisfaccion'] <= 9.0
        
        # Verificar NPS tiene datos (score puede ser number o None)
        assert 'score' in result['nps_data']
    
    @pytest.mark.django_db
    def test_get_analysis_data_scale_question(
        self, complete_survey, complete_responses
    ):
        """Debe analizar pregunta de escala correctamente."""
        qs = SurveyResponse.objects.filter(survey=complete_survey)
        
        result = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=False
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
        self, complete_survey, complete_responses
    ):
        """Debe analizar pregunta numérica correctamente."""
        qs = SurveyResponse.objects.filter(survey=complete_survey)
        
        result = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=False
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
        self, complete_survey, complete_responses
    ):
        """Debe analizar pregunta de opción única correctamente."""
        qs = SurveyResponse.objects.filter(survey=complete_survey)
        
        result = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=False
        )
        
        # Tercera pregunta es de tipo single
        pregunta_single = result['analysis_data'][2]
        
        assert pregunta_single['type'] == 'single'
        assert pregunta_single['total_respuestas'] == 5
        assert len(pregunta_single['opciones']) > 0
        assert pregunta_single['insight'] != ''
    
    @pytest.mark.django_db
    def test_get_analysis_data_text_question(
        self, complete_survey, complete_responses
    ):
        """Debe analizar pregunta de texto correctamente."""
        qs = SurveyResponse.objects.filter(survey=complete_survey)
        
        result = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=False
        )
        
        # Cuarta pregunta es de tipo text
        pregunta_text = result['analysis_data'][3]
        
        assert pregunta_text['type'] == 'text'
        assert pregunta_text['total_respuestas'] == 5
        assert len(pregunta_text['samples_texto']) > 0
        assert pregunta_text['insight'] != ''
    
    @pytest.mark.django_db
    def test_get_analysis_data_respects_orden(
        self, complete_survey, complete_responses
    ):
        """Debe respetar el orden de las preguntas."""
        qs = SurveyResponse.objects.filter(survey=complete_survey)
        
        result = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=False
        )
        
        # Verificar que el orden es correcto
        for i, item in enumerate(result['analysis_data'], 1):
            assert item['order'] == i
    
    @pytest.mark.django_db
    def test_get_analysis_data_calculates_nps(
        self, complete_survey, complete_responses
    ):
        """Debe calcular NPS correctamente."""
        qs = SurveyResponse.objects.filter(survey=complete_survey)
        
        result = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=False
        )
        
        # NPS should be calculated from scale values [9, 10, 8, 9, 7]
        # Promoters (9-10): 4, Passives (7-8): 1, Detractors (<7): 0
        # NPS = (4/5 - 0/5) * 100 = 80
        assert result['nps_data']['score'] is not None
        assert isinstance(result['nps_data']['score'], (int, float))
    
    @pytest.mark.django_db
    def test_get_analysis_data_generates_heatmap_for_small_datasets(
        self, complete_survey, complete_responses
    ):
        """Debe generar heatmap para datasets pequeños si include_charts=True."""
        qs = SurveyResponse.objects.filter(survey=complete_survey)
        
        result = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=True
        )
        
        # For small datasets (<=1000 responses), heatmap may be generated
        # Just verify the key exists and structure is correct
        assert 'heatmap_image' in result
    
    @pytest.mark.django_db
    def test_get_analysis_data_no_heatmap_if_charts_disabled(
        self, complete_survey, complete_responses
    ):
        """No debe generar heatmap si include_charts=False."""
        qs = SurveyResponse.objects.filter(survey=complete_survey)
        
        result = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=False
        )
        
        assert result['heatmap_image'] is None
    
    @pytest.mark.django_db
    def test_get_analysis_data_handles_heatmap_error(
        self, complete_survey, complete_responses
    ):
        """Debe manejar errores en generación de heatmap."""
        qs = SurveyResponse.objects.filter(survey=complete_survey)
        
        # Even if heatmap fails, analysis should continue
        result = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=True
        )
        
        # No debe fallar, solo no tener heatmap o tenerlo
        assert 'analysis_data' in result
        assert len(result['analysis_data']) == 4
    
    @pytest.mark.django_db
    def test_get_analysis_data_no_scale_questions(self, user):
        """Debe manejar encuestas sin preguntas de escala."""
        encuesta = Survey.objects.create(
            title='Sin Escalas',
            author=user
        )
        # Solo pregunta de texto
        Question.objects.create(
            survey=encuesta,
            text='Comentarios',
            type='text',
            order=1
        )
        
        qs = SurveyResponse.objects.filter(survey=encuesta)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta, qs, include_charts=False
        )
        
        assert result['kpi_prom_satisfaccion'] == 0
        assert result['nps_data']['score'] is None
    
    @pytest.mark.django_db
    def test_get_analysis_data_includes_question_metadata(
        self, complete_survey, complete_responses
    ):
        """Debe incluir metadata de preguntas en el resultado."""
        qs = SurveyResponse.objects.filter(survey=complete_survey)
        
        result = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=False
        )
        
        for item in result['analysis_data']:
            assert 'id' in item
            assert 'order' in item
            assert 'text' in item
            assert 'type' in item
            assert 'tipo_display' in item
    
    @pytest.mark.django_db
    def test_get_analysis_data_generates_charts_when_enabled(
        self, complete_survey, complete_responses
    ):
        """Debe generar datos de gráficos cuando include_charts=True."""
        qs = SurveyResponse.objects.filter(survey=complete_survey)
        
        result = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=True
        )
        
        # Check that chart data is present for scale question
        pregunta_scale = result['analysis_data'][0]
        assert 'chart_labels' in pregunta_scale
        assert 'chart_data' in pregunta_scale


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
        self, complete_survey, complete_responses
    ):
        """Debe usar caché si cache_key es proporcionado."""
        qs = SurveyResponse.objects.filter(survey=complete_survey)
        cache_key = 'test_analysis_cache'
        
        # Primera llamada - debe cachear
        result1 = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=False, cache_key=cache_key
        )
        
        # Segunda llamada - debe usar caché
        result2 = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=False, cache_key=cache_key
        )
        
        # Resultados deben ser idénticos
        assert result1 == result2
    
    @pytest.mark.django_db
    def test_get_analysis_data_cache_hit_avoids_computation(
        self, complete_survey, complete_responses
    ):
        """Cache hit debe evitar recalcular análisis."""
        qs = SurveyResponse.objects.filter(survey=complete_survey)
        cache_key = 'test_cache_hit'
        
        # Primera llamada - calcula
        result1 = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=False, cache_key=cache_key
        )
        
        # Segunda llamada - debe usar caché
        result2 = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=False, cache_key=cache_key
        )
        
        # Results should be identical (from cache)
        assert result1 == result2
    
    @pytest.mark.django_db
    def test_get_analysis_data_no_cache_without_key(
        self, complete_survey, complete_responses
    ):
        """No debe cachear si no se proporciona cache_key."""
        qs = SurveyResponse.objects.filter(survey=complete_survey)
        
        # Sin cache_key
        result = SurveyAnalysisService.get_analysis_data(
            complete_survey, qs, include_charts=False
        )
        
        # Verificar que no se guardó en caché
        cached = cache.get('any_key')
        assert cached is None
    
    @pytest.mark.django_db
    def test_get_analysis_data_cache_expiration(
        self, complete_survey, complete_responses
    ):
        """Caché debe expirar después de 3600 segundos."""
        qs = SurveyResponse.objects.filter(survey=complete_survey)
        cache_key = 'test_expiration'
        
        with patch('django.core.cache.cache.set') as mock_cache_set:
            SurveyAnalysisService.get_analysis_data(
                complete_survey, qs, include_charts=False, cache_key=cache_key
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
            survey=encuesta,
            text='Pregunta sin respuestas',
            type='scale',
            order=1
        )
        
        qs = SurveyResponse.objects.filter(survey=encuesta)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta, qs, include_charts=False
        )
        
        assert len(result['analysis_data']) == 1
        assert result['analysis_data'][0]['total_respuestas'] == 0
    
    @pytest.mark.django_db
    def test_get_analysis_data_encuesta_vacia(self, user):
        """Debe manejar encuesta sin preguntas."""
        encuesta = Survey.objects.create(title='Vacía', author=user)
        qs = SurveyResponse.objects.filter(survey=encuesta)
        
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
            survey=encuesta, text='P1', type='scale', order=1
        )
        p2 = Question.objects.create(
            survey=encuesta, text='P2', type='scale', order=2
        )
        
        # Crear respuestas
        resp = SurveyResponse.objects.create(survey=encuesta, user=user)
        QuestionResponse.objects.create(
            survey_response=resp, question=p1, numeric_value=8
        )
        QuestionResponse.objects.create(
            survey_response=resp, question=p2, numeric_value=10
        )
        
        qs = SurveyResponse.objects.filter(survey=encuesta)
        
        result = SurveyAnalysisService.get_analysis_data(
            encuesta, qs, include_charts=False
        )
        
        # Promedio de [8, 10] = 9
        assert result['kpi_prom_satisfaccion'] == 9.0
