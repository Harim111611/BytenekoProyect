"""
Tests para core/services/analysis_service.py
Tests unitarios para TextAnalyzer, DataFrameBuilder, QuestionAnalyzer y NPSCalculator
"""
import pytest
import collections
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal

from django.contrib.auth.models import User
from surveys.models import (
    Survey, Question, AnswerOption, SurveyResponse, QuestionResponse
)
from core.services.analysis_service import (
    TextAnalyzer,
    DataFrameBuilder,
    QuestionAnalyzer,
    NPSCalculator
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def user():
    """Test user."""
    return User.objects.create_user(username='testuser', password='12345')

@pytest.fixture
def survey(user):
    """Test survey."""
    return Survey.objects.create(
        title='Test Survey',
        description='Test description',
        author=user,
        status='active'
    )

@pytest.fixture
def question_text(survey):
    """Text question."""
    return Question.objects.create(
        survey=survey,
        text='How did you like it?',
        type='text',
        order=1
    )

@pytest.fixture
def question_scale(survey):
    """Scale question."""
    return Question.objects.create(
        survey=survey,
        text='How likely are you to recommend?',
        type='scale',
        order=2
    )

@pytest.fixture
def question_number(survey):
    """Number question."""
    return Question.objects.create(
        survey=survey,
        text='How old are you?',
        type='number',
        order=3
    )

@pytest.fixture
def question_single(survey):
    """Single choice question."""
    question = Question.objects.create(
        survey=survey,
        text='What is your favorite color?',
        type='single',
        order=4
    )
    AnswerOption.objects.create(question=question, text='Red')
    AnswerOption.objects.create(question=question, text='Blue')
    AnswerOption.objects.create(question=question, text='Green')
    return question

@pytest.fixture
def question_multi(survey):
    """Multiple choice question."""
    question = Question.objects.create(
        survey=survey,
        text='Which fruits do you like?',
        type='multi',
        order=5
    )
    AnswerOption.objects.create(question=question, text='Apple')
    AnswerOption.objects.create(question=question, text='Orange')
    AnswerOption.objects.create(question=question, text='Banana')
    return question

@pytest.fixture
def survey_response(survey, user):
    """Test SurveyResponse."""
    return SurveyResponse.objects.create(
        survey=survey,
        user=user
    )


# ============================================================================
# TESTS: TextAnalyzer
# ============================================================================

class TestTextAnalyzer:
    """Tests for TextAnalyzer."""

    def test_spanish_stopwords_defined(self):
        assert len(TextAnalyzer.SPANISH_STOPWORDS) > 0
        assert 'de' in TextAnalyzer.SPANISH_STOPWORDS
        assert 'el' in TextAnalyzer.SPANISH_STOPWORDS

    @pytest.mark.django_db
    def test_analyze_text_responses_empty_queryset(self, question_text):
        qs = QuestionResponse.objects.filter(question=question_text)
        words, bigrams, *_ = TextAnalyzer.analyze_text_responses(qs)
        assert words == []
        assert bigrams == []

    @pytest.mark.django_db
    def test_analyze_text_responses_with_data(self, question_text, survey_response):
        QuestionResponse.objects.create(
            survey_response=survey_response,
            question=question_text,
            text_value='The product is very good and excellent'
        )
        QuestionResponse.objects.create(
            survey_response=survey_response,
            question=question_text,
            text_value='The service is excellent and very professional'
        )
        qs = QuestionResponse.objects.filter(question=question_text)
        words, bigrams, *_ = TextAnalyzer.analyze_text_responses(qs)
        assert len(words) > 0
        word_list = [w[0] for w in words]
        assert 'excelente' in word_list or 'excellent' in word_list
        assert 'el' not in word_list
        assert len(bigrams) > 0

    @pytest.mark.django_db
    def test_analyze_text_filters_short_words(self, question_text, survey_response):
        QuestionResponse.objects.create(
            survey_response=survey_response,
            question=question_text,
            text_value='I am so in'
        )
        qs = QuestionResponse.objects.filter(question=question_text)
        words, *_ = TextAnalyzer.analyze_text_responses(qs)
        word_list = [w[0] for w in words]
        assert 'i' not in word_list
        assert 'am' not in word_list
        assert 'so' not in word_list

    @pytest.mark.django_db
    def test_analyze_text_max_texts_limit(self, question_text, survey_response):
        for i in range(10):
            QuestionResponse.objects.create(
                survey_response=survey_response,
                question=question_text,
                text_value=f'Text {i} analysis test'
            )
        qs = QuestionResponse.objects.filter(question=question_text)
        words, bigrams, *_ = TextAnalyzer.analyze_text_responses(qs, max_texts=5)
        assert len(words) > 0
        assert len(bigrams) > 0


# ============================================================================
# TESTS: DataFrameBuilder
# ============================================================================

class TestDataFrameBuilder:
    """Tests para DataFrameBuilder."""
    
    @pytest.mark.django_db
    def test_build_responses_dataframe_empty(self, survey):
        """Should return empty DataFrame if there are no responses."""
        qs = SurveyResponse.objects.filter(survey=survey)
        df = DataFrameBuilder.build_responses_dataframe(survey, qs)
        assert df.empty
    
    @pytest.mark.django_db
    def test_build_responses_dataframe_with_data(
        self, survey, user, question_text, question_scale
    ):
        """Should build DataFrame with responses."""
        # Create responses
        resp1 = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp1,
            question=question_text,
            text_value='Good'
        )
        QuestionResponse.objects.create(
            survey_response=resp1,
            question=question_scale,
            numeric_value=9
        )
        
        resp2 = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp2,
            question=question_text,
            text_value='Excellent'
        )
        QuestionResponse.objects.create(
            survey_response=resp2,
            question=question_scale,
            numeric_value=10
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        df = DataFrameBuilder.build_responses_dataframe(survey, qs)
        
        assert not df.empty
        assert len(df) == 2  # 2 responses
        # The columns should be the question texts
        assert 'How did you like it?' in df.columns
        assert 'How likely are you to recommend?' in df.columns
    
    @pytest.mark.django_db
    def test_build_responses_dataframe_handles_errors(self, survey):
        """Should return empty DataFrame if there is a pivot error."""
        qs = SurveyResponse.objects.filter(survey=survey)
        
        with patch('pandas.DataFrame.pivot_table', side_effect=Exception('Error')):
            df = DataFrameBuilder.build_responses_dataframe(survey, qs)
            assert df.empty


# ============================================================================
# TESTS: QuestionAnalyzer - Numeric Questions
# ============================================================================

class TestQuestionAnalyzerNumeric:
    """Tests para análisis de preguntas numéricas."""
    
    @pytest.mark.django_db
    def test_analyze_numeric_no_responses(self, question_scale, survey):
        """Should return basic structure with no responses."""
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_numeric_question(question_scale, qs)
        
        assert result['total_respuestas'] == 0
        assert result['estadisticas'] is None
        assert result['avg'] is None
        assert result['chart_image'] is None
    
    @pytest.mark.django_db
    def test_analyze_numeric_with_scale_responses(
        self, question_scale, survey, user
    ):
        """Should correctly analyze scale question."""
        # Create responses
        for value in [9, 10, 8, 9, 10]:
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=question_scale,
                numeric_value=value
            )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_numeric_question(question_scale, qs)
        
        assert result['total_respuestas'] == 5
        assert result['estadisticas'] is not None
        assert result['estadisticas']['minimo'] == 8
        assert result['estadisticas']['maximo'] == 10
        assert result['estadisticas']['promedio'] == 9.2
        assert result['estadisticas']['mediana'] == 9
        assert result['avg'] == 9.2
        assert result['scale_cap'] == 10
        assert 'Excelente' in result['insight']
    
    @pytest.mark.django_db
    def test_analyze_numeric_with_number_responses(
        self, question_number, survey, user
    ):
        """Should correctly analyze number question."""
        # Create responses
        for value in [25, 30, 28, 35]:
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=question_number,
                numeric_value=value
            )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_numeric_question(question_number, qs)
        
        assert result['total_respuestas'] == 4
        assert result['estadisticas']['promedio'] == 29.5
        assert result['avg'] == 29.5
    
    @pytest.mark.django_db
    def test_analyze_numeric_sentimiento_excelente(
        self, question_scale, survey, user
    ):
        """Should classify as 'Excelente' if average >= 8."""
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=question_scale,
            numeric_value=9
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_numeric_question(question_scale, qs)
        
        assert 'Excelente' in result['insight']
    
    @pytest.mark.django_db
    def test_analyze_numeric_sentimiento_bueno(
        self, question_scale, survey, user
    ):
        """Should classify as 'Bueno' if average between 6 and 8."""
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=question_scale,
            numeric_value=7
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_numeric_question(question_scale, qs)
        
        assert 'Bueno' in result['insight']
    
    @pytest.mark.django_db
    def test_analyze_numeric_sentimiento_critico(
        self, question_scale, survey, user
    ):
        """Should classify as 'Crítico' if average <= 4."""
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=question_scale,
            numeric_value=3
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_numeric_question(question_scale, qs)
        
        assert 'Bueno' in result['insight']
    
    @pytest.mark.django_db
    @patch('core.services.analysis_service.ChartGenerator.generate_vertical_bar_chart')
    def test_analyze_numeric_generates_chart(
        self, mock_chart, question_scale, survey, user
    ):
        """Should generate chart if include_charts=True."""
        mock_chart.return_value = 'fake_chart_image'
        
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=question_scale,
            numeric_value=9
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_numeric_question(
            question_scale, qs, include_charts=True
        )
        
        assert result['chart_image'] == 'fake_chart_image'
        assert result['chart_data'] is not None
        mock_chart.assert_called_once()
    
    @pytest.mark.django_db
    def test_analyze_numeric_no_chart_if_disabled(
        self, question_scale, survey, user
    ):
        """Should not generate chart if include_charts=False."""
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=question_scale,
            numeric_value=9
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_numeric_question(
            question_scale, qs, include_charts=False
        )
        
        assert result['chart_image'] is None


# ============================================================================
# TESTS: QuestionAnalyzer - Choice Questions
# ============================================================================

class TestQuestionAnalyzerChoice:
    """Tests para análisis de preguntas de opción."""
    
    @pytest.mark.django_db
    def test_analyze_choice_no_responses(self, question_single, survey):
        """Should return basic structure with no responses."""
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_choice_question(question_single, qs)
        
        assert result['total_respuestas'] == 0
        assert result['opciones'] == []
        assert 'Sin datos suficientes para generar un análisis.' in result['insight']
    
    @pytest.mark.django_db
    def test_analyze_choice_single_with_responses(
        self, question_single, survey, user
    ):
        """Should correctly analyze single choice question."""
        # Create responses
        option_red = question_single.options.get(text='Red')
        option_blue = question_single.options.get(text='Blue')
        
        # 3 votes for Red, 2 for Blue
        for _ in range(3):
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=question_single,
                selected_option=option_red
            )
        
        for _ in range(2):
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=question_single,
                selected_option=option_blue
            )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_choice_question(question_single, qs)
        
        assert result['total_respuestas'] == 5
        assert len(result['opciones']) == 2
        assert result['opciones'][0]['label'] == 'Red'
        assert result['opciones'][0]['count'] == 3
        assert result['opciones'][0]['percent'] == 60.0
        assert 'Red' in result['insight']
        assert '60%' in result['insight']
    
    @pytest.mark.django_db
    def test_analyze_choice_multi_with_text_values(
        self, question_multi, survey, user
    ):
        """Should analyze multi choice question with text values."""
        # Simulate multiple responses in text_value
        resp1 = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp1,
            question=question_multi,
            text_value='Apple, Orange'
        )
        
        resp2 = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp2,
            question=question_multi,
            text_value='Apple, Banana'
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_choice_question(question_multi, qs)
        
        assert result['total_respuestas'] == 2
        # Apple should appear 2 times
        apple_opt = next(o for o in result['opciones'] if o['label'] == 'Apple')
        assert apple_opt['count'] == 2
    
    @pytest.mark.django_db
    @patch('core.services.analysis_service.ChartGenerator.generate_horizontal_bar_chart')
    def test_analyze_choice_generates_chart(
        self, mock_chart, question_single, survey, user
    ):
        """Should generate chart if include_charts=True."""
        mock_chart.return_value = 'fake_horizontal_chart'
        
        option = question_single.options.first()
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=question_single,
            selected_option=option
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_choice_question(
            question_single, qs, include_charts=True
        )
        
        assert isinstance(result['chart_image'], str)
        assert result['chart_image']


# ============================================================================
# TESTS: QuestionAnalyzer - Text Questions
# ============================================================================

class TestQuestionAnalyzerText:
    """Tests para análisis de preguntas de texto."""
    
    @pytest.mark.django_db
    def test_analyze_text_no_responses(self, question_text, survey):
        """Should return basic structure with no responses."""
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_text_question(question_text, qs)
        
        assert result['total_respuestas'] == 0
        assert result['samples_texto'] == []
    
    @pytest.mark.django_db
    def test_analyze_text_with_responses(
        self, question_text, survey, user
    ):
        """Should analyze text responses and extract samples."""
        # Create responses
        texts = [
            'Excellent service',
            'Very good product',
            'Superior quality',
            'Great experience'
        ]
        
        for text in texts:
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=question_text,
                text_value=text
            )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_text_question(question_text, qs)
        
        assert result['total_respuestas'] == 4
        assert len(result['samples_texto']) <= 5  # Max 5 samples
        assert result['insight'] != ''
    
    @pytest.mark.django_db
    @patch('core.services.analysis_service.TextAnalyzer.analyze_text_responses')
    def test_analyze_text_with_keywords(
        self, mock_analyzer, question_text, survey, user
    ):
        """Should show keywords in insight."""
        mock_analyzer.return_value = (
            [('excellent', 5), ('product', 3), ('quality', 2)],
            [],
            None
        )
        
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=question_text,
            text_value='Test'
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_text_question(question_text, qs)
        
        assert 'excellent' in result['insight']
    
    @pytest.mark.django_db
    @patch('core.services.analysis_service.TextAnalyzer.analyze_text_responses')
    def test_analyze_text_no_keywords(
        self, mock_analyzer, question_text, survey, user
    ):
        """Should show message about dispersed responses if no keywords."""
        mock_analyzer.return_value = ([], [], None)
        
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=question_text,
            text_value='Test'
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_text_question(question_text, qs)
        
        assert 'Aún no hay suficientes comentarios de encuestados.' in result['insight']


# ============================================================================
# TESTS: NPSCalculator
# ============================================================================

class TestNPSCalculator:
    """Tests para NPSCalculator."""
    
    @pytest.mark.django_db
    def test_calculate_nps_no_pregunta(self, survey):
        """Should return None if there is no question."""
        qs = SurveyResponse.objects.filter(survey=survey)
        result = NPSCalculator.calculate_nps(None, qs)
        
        assert result['score'] is None
        assert result['breakdown_chart'] is None
    
    @pytest.mark.django_db
    def test_calculate_nps_no_responses(self, question_scale, survey):
        """Should return None if there are no responses."""
        qs = SurveyResponse.objects.filter(survey=survey)
        result = NPSCalculator.calculate_nps(question_scale, qs)
        
        assert result['score'] is None
    
    @pytest.mark.django_db
    def test_calculate_nps_promotores_only(
        self, question_scale, survey, user
    ):
        """Should calculate NPS=100 if all are promoters."""
        # Promoters: 9-10
        for value in [9, 10, 9, 10]:
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=question_scale,
                numeric_value=value
            )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = NPSCalculator.calculate_nps(question_scale, qs)
        
        assert result['score'] == 100.0
    
    @pytest.mark.django_db
    def test_calculate_nps_detractores_only(
        self, question_scale, survey, user
    ):
        """Should calculate NPS=-100 if all are detractors."""
        # Detractors: 0-6
        for value in [3, 4, 5, 6]:
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=question_scale,
                numeric_value=value
            )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = NPSCalculator.calculate_nps(question_scale, qs)
        
        assert result['score'] == -100.0
    
    @pytest.mark.django_db
    def test_calculate_nps_mixed_responses(
        self, question_scale, survey, user
    ):
        """Should correctly calculate NPS with mixed responses."""
        # 5 promoters (9-10), 3 passives (7-8), 2 detractors (0-6)
        values = [9, 10, 9, 10, 9, 7, 8, 7, 5, 6]
        
        for value in values:
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=question_scale,
                numeric_value=value
            )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = NPSCalculator.calculate_nps(question_scale, qs)
        
        # NPS = (5/10 * 100) - (2/10 * 100) = 50 - 20 = 30
        assert result['score'] == 30.0
    
    @pytest.mark.django_db
    @patch('core.services.analysis_service.ChartGenerator.generate_nps_chart')
    def test_calculate_nps_generates_chart(
        self, mock_chart, question_scale, survey, user
    ):
        """Should generate chart if include_chart=True."""
        mock_chart.return_value = 'fake_nps_chart'
        
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=question_scale,
            numeric_value=9
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = NPSCalculator.calculate_nps(question_scale, qs, include_chart=True)
        
        assert result['breakdown_chart'] == 'fake_nps_chart'
        mock_chart.assert_called_once()
    
    @pytest.mark.django_db
    def test_calculate_nps_no_chart_if_disabled(
        self, question_scale, survey, user
    ):
        """Should not generate chart if include_chart=False."""
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=question_scale,
            numeric_value=9
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = NPSCalculator.calculate_nps(question_scale, qs, include_chart=False)
        
        assert result['breakdown_chart'] is None
    
    @pytest.mark.django_db
    def test_calculate_nps_pasivos_not_counted(
        self, question_scale, survey, user
    ):
        """Passives (7-8) should not affect NPS score."""
        # Only passives
        for value in [7, 8, 7, 8]:
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=question_scale,
                numeric_value=value
            )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = NPSCalculator.calculate_nps(question_scale, qs)
        
        # NPS = (0% promoters) - (0% detractors) = 0
        assert result['score'] == 0.0
