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
    Encuesta, Pregunta, OpcionRespuesta,
    RespuestaEncuesta, RespuestaPregunta
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
    """Usuario de prueba."""
    return User.objects.create_user(username='testuser', password='12345')


@pytest.fixture
def encuesta(user):
    """Encuesta de prueba."""
    return Survey.objects.create(
        title='Test Survey',
        description='Test description',
        author=user,
        status='active'
    )


@pytest.fixture
def pregunta_text(encuesta):
    """Pregunta de tipo texto."""
    return Question.objects.create(
        survey=survey,
        text='¿Qué te pareció?',
        type='text',
        order=1
    )


@pytest.fixture
def pregunta_scale(encuesta):
    """Pregunta de tipo escala."""
    return Question.objects.create(
        survey=survey,
        text='¿Qué tan probable es que recomiendes?',
        type='scale',
        order=2
    )


@pytest.fixture
def pregunta_number(encuesta):
    """Pregunta de tipo número."""
    return Question.objects.create(
        survey=survey,
        text='¿Cuántos años tienes?',
        type='number',
        order=3
    )


@pytest.fixture
def pregunta_single(encuesta):
    """Pregunta de opción única."""
    pregunta = Question.objects.create(
        survey=survey,
        text='¿Cuál es tu color favorito?',
        type='single',
        order=4
    )
    # Crear opciones (OpcionRespuesta no tiene campo 'orden')
    AnswerOption.objects.create(question=question, text='Rojo')
    AnswerOption.objects.create(question=question, text='Azul')
    AnswerOption.objects.create(question=question, text='Verde')
    return pregunta


@pytest.fixture
def pregunta_multi(encuesta):
    """Pregunta de opción múltiple."""
    pregunta = Question.objects.create(
        survey=survey,
        text='¿Qué frutas te gustan?',
        type='multi',
        order=5
    )
    AnswerOption.objects.create(question=question, text='Manzana')
    AnswerOption.objects.create(question=question, text='Naranja')
    AnswerOption.objects.create(question=question, text='Plátano')
    return pregunta


@pytest.fixture
def respuesta_encuesta(encuesta, user):
    """RespuestaEncuesta de prueba."""
    return SurveyResponse.objects.create(
        survey=encuesta,
        user=user
    )


# ============================================================================
# TESTS: TextAnalyzer
# ============================================================================

class TestTextAnalyzer:
    """Tests para TextAnalyzer."""
    
    def test_spanish_stopwords_defined(self):
        """Debe tener stopwords en español definidas."""
        assert len(TextAnalyzer.SPANISH_STOPWORDS) > 0
        assert 'de' in TextAnalyzer.SPANISH_STOPWORDS
        assert 'el' in TextAnalyzer.SPANISH_STOPWORDS
    
    @pytest.mark.django_db
    def test_analyze_text_responses_empty_queryset(self, pregunta_text):
        """Debe retornar listas vacías si no hay textos."""
        qs = QuestionResponse.objects.filter(question=pregunta_text)
        words, bigrams = TextAnalyzer.analyze_text_responses(qs)
        
        assert words == []
        assert bigrams == []
    
    @pytest.mark.django_db
    def test_analyze_text_responses_with_data(self, pregunta_text, respuesta_encuesta):
        """Debe analizar textos y retornar palabras y bigramas."""
        # Crear respuestas
        QuestionResponse.objects.create(
            survey_response=respuesta_encuesta,
            question=pregunta_text,
            text_value='El producto es muy bueno y excelente'
        )
        QuestionResponse.objects.create(
            survey_response=respuesta_encuesta,
            question=pregunta_text,
            text_value='El servicio es excelente y muy profesional'
        )
        
        qs = QuestionResponse.objects.filter(question=pregunta_text)
        words, bigrams = TextAnalyzer.analyze_text_responses(qs)
        
        # Debe haber palabras (sin stopwords)
        assert len(words) > 0
        # Debe filtrar stopwords ('el', 'es', 'muy', 'y')
        word_list = [w[0] for w in words]
        assert 'excelente' in word_list
        assert 'el' not in word_list  # stopword
        
        # Debe haber bigramas
        assert len(bigrams) > 0
    
    @pytest.mark.django_db
    def test_analyze_text_filters_short_words(self, pregunta_text, respuesta_encuesta):
        """Debe filtrar palabras cortas (<=2 caracteres)."""
        QuestionResponse.objects.create(
            survey_response=respuesta_encuesta,
            question=pregunta_text,
            text_value='Yo sé que tu no me amas'
        )
        
        qs = QuestionResponse.objects.filter(question=pregunta_text)
        words, _ = TextAnalyzer.analyze_text_responses(qs)
        
        word_list = [w[0] for w in words]
        assert 'yo' not in word_list  # <=2 chars
        assert 'tu' not in word_list  # <=2 chars
        assert 'me' not in word_list  # <=2 chars
    
    @pytest.mark.django_db
    def test_analyze_text_max_texts_limit(self, pregunta_text, respuesta_encuesta):
        """Debe respetar el límite de max_texts."""
        # Crear 10 respuestas
        for i in range(10):
            QuestionResponse.objects.create(
                survey_response=respuesta_encuesta,
                question=pregunta_text,
                text_value=f'Texto {i} prueba análisis'
            )
        
        qs = QuestionResponse.objects.filter(question=pregunta_text)
        
        # Limitar a 5 textos
        words, bigrams = TextAnalyzer.analyze_text_responses(qs, max_texts=5)
        
        assert len(words) > 0
        assert len(bigrams) > 0


# ============================================================================
# TESTS: DataFrameBuilder
# ============================================================================

class TestDataFrameBuilder:
    """Tests para DataFrameBuilder."""
    
    @pytest.mark.django_db
    def test_build_responses_dataframe_empty(self, encuesta):
        """Debe retornar DataFrame vacío si no hay respuestas."""
        qs = SurveyResponse.objects.filter(survey=survey)
        df = DataFrameBuilder.build_responses_dataframe(encuesta, qs)
        
        assert df.empty
    
    @pytest.mark.django_db
    def test_build_responses_dataframe_with_data(
        self, encuesta, user, pregunta_text, pregunta_scale
    ):
        """Debe construir DataFrame con respuestas."""
        # Crear respuestas
        resp1 = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp1,
            question=pregunta_text,
            text_value='Bueno'
        )
        QuestionResponse.objects.create(
            survey_response=resp1,
            question=pregunta_scale,
            numeric_value=9
        )
        
        resp2 = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp2,
            question=pregunta_text,
            text_value='Excelente'
        )
        QuestionResponse.objects.create(
            survey_response=resp2,
            question=pregunta_scale,
            numeric_value=10
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        df = DataFrameBuilder.build_responses_dataframe(encuesta, qs)
        
        assert not df.empty
        assert len(df) == 2  # 2 respuestas
        assert 'Fecha' in df.columns
    
    @pytest.mark.django_db
    def test_build_responses_dataframe_handles_errors(self, encuesta):
        """Debe retornar DataFrame vacío si hay error en pivot."""
        qs = SurveyResponse.objects.filter(survey=survey)
        
        with patch('pandas.DataFrame.pivot_table', side_effect=Exception('Error')):
            df = DataFrameBuilder.build_responses_dataframe(encuesta, qs)
            assert df.empty


# ============================================================================
# TESTS: QuestionAnalyzer - Numeric Questions
# ============================================================================

class TestQuestionAnalyzerNumeric:
    """Tests para análisis de preguntas numéricas."""
    
    @pytest.mark.django_db
    def test_analyze_numeric_no_responses(self, pregunta_scale, encuesta):
        """Debe retornar estructura básica sin respuestas."""
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_numeric_question(pregunta_scale, qs)
        
        assert result['total_respuestas'] == 0
        assert result['estadisticas'] is None
        assert result['avg'] is None
        assert result['chart_image'] is None
    
    @pytest.mark.django_db
    def test_analyze_numeric_with_scale_responses(
        self, pregunta_scale, encuesta, user
    ):
        """Debe analizar pregunta de tipo scale correctamente."""
        # Crear respuestas
        for valor in [9, 10, 8, 9, 10]:
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=pregunta_scale,
                numeric_value=valor
            )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_numeric_question(pregunta_scale, qs)
        
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
        self, pregunta_number, encuesta, user
    ):
        """Debe analizar pregunta de tipo number correctamente."""
        # Crear respuestas
        for valor in [25, 30, 28, 35]:
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=pregunta_number,
                numeric_value=valor
            )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_numeric_question(pregunta_number, qs)
        
        assert result['total_respuestas'] == 4
        assert result['estadisticas']['promedio'] == 29.5
        assert result['avg'] == 29.5
    
    @pytest.mark.django_db
    def test_analyze_numeric_sentimiento_excelente(
        self, pregunta_scale, encuesta, user
    ):
        """Debe clasificar como 'Excelente' si promedio >= 8."""
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=pregunta_scale,
            numeric_value=9
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_numeric_question(pregunta_scale, qs)
        
        assert 'Excelente' in result['insight']
    
    @pytest.mark.django_db
    def test_analyze_numeric_sentimiento_bueno(
        self, pregunta_scale, encuesta, user
    ):
        """Debe clasificar como 'Bueno' si promedio entre 6 y 8."""
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=pregunta_scale,
            numeric_value=7
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_numeric_question(pregunta_scale, qs)
        
        assert 'Bueno' in result['insight']
    
    @pytest.mark.django_db
    def test_analyze_numeric_sentimiento_critico(
        self, pregunta_scale, encuesta, user
    ):
        """Debe clasificar como 'Crítico' si promedio <= 4."""
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=pregunta_scale,
            numeric_value=3
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_numeric_question(pregunta_scale, qs)
        
        assert 'Crítico' in result['insight']
    
    @pytest.mark.django_db
    @patch('core.services.analysis_service.ChartGenerator.generate_vertical_bar_chart')
    def test_analyze_numeric_generates_chart(
        self, mock_chart, pregunta_scale, encuesta, user
    ):
        """Debe generar gráfico si include_charts=True."""
        mock_chart.return_value = 'fake_chart_image'
        
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=pregunta_scale,
            numeric_value=9
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_numeric_question(
            pregunta_scale, qs, include_charts=True
        )
        
        assert result['chart_image'] == 'fake_chart_image'
        assert result['chart_data'] is not None
        mock_chart.assert_called_once()
    
    @pytest.mark.django_db
    def test_analyze_numeric_no_chart_if_disabled(
        self, pregunta_scale, encuesta, user
    ):
        """No debe generar gráfico si include_charts=False."""
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=pregunta_scale,
            numeric_value=9
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_numeric_question(
            pregunta_scale, qs, include_charts=False
        )
        
        assert result['chart_image'] is None


# ============================================================================
# TESTS: QuestionAnalyzer - Choice Questions
# ============================================================================

class TestQuestionAnalyzerChoice:
    """Tests para análisis de preguntas de opción."""
    
    @pytest.mark.django_db
    def test_analyze_choice_no_responses(self, pregunta_single, encuesta):
        """Debe retornar estructura básica sin respuestas."""
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_choice_question(pregunta_single, qs)
        
        assert result['total_respuestas'] == 0
        assert result['opciones'] == []
        assert 'Aún no hay respuestas' in result['insight']
    
    @pytest.mark.django_db
    def test_analyze_choice_single_with_responses(
        self, pregunta_single, encuesta, user
    ):
        """Debe analizar pregunta single correctamente."""
        # Crear respuestas
        opcion_roja = pregunta_single.options.get(text='Rojo')
        opcion_azul = pregunta_single.options.get(text='Azul')
        
        # 3 votos para Rojo, 2 para Azul
        for _ in range(3):
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=pregunta_single,
                selected_option=opcion_roja
            )
        
        for _ in range(2):
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=pregunta_single,
                selected_option=opcion_azul
            )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_choice_question(pregunta_single, qs)
        
        assert result['total_respuestas'] == 5
        assert len(result['opciones']) == 2
        assert result['opciones'][0]['label'] == 'Rojo'
        assert result['opciones'][0]['count'] == 3
        assert result['opciones'][0]['percent'] == 60.0
        assert 'Rojo' in result['insight']
        assert '60%' in result['insight']
    
    @pytest.mark.django_db
    def test_analyze_choice_multi_with_text_values(
        self, pregunta_multi, encuesta, user
    ):
        """Debe analizar pregunta multi con valores de texto."""
        # Simular respuestas múltiples en valor_texto
        resp1 = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp1,
            question=pregunta_multi,
            text_value='Manzana, Naranja'
        )
        
        resp2 = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp2,
            question=pregunta_multi,
            text_value='Manzana, Plátano'
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_choice_question(pregunta_multi, qs)
        
        assert result['total_respuestas'] == 2
        # Manzana debe aparecer 2 veces
        manzana_opt = next(o for o in result['opciones'] if o['label'] == 'Manzana')
        assert manzana_opt['count'] == 2
    
    @pytest.mark.django_db
    @patch('core.services.analysis_service.ChartGenerator.generate_horizontal_bar_chart')
    def test_analyze_choice_generates_chart(
        self, mock_chart, pregunta_single, encuesta, user
    ):
        """Debe generar gráfico si include_charts=True."""
        mock_chart.return_value = 'fake_horizontal_chart'
        
        opcion = pregunta_single.options.first()
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=pregunta_single,
            selected_option=selected_option
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_choice_question(
            pregunta_single, qs, include_charts=True
        )
        
        assert result['chart_image'] == 'fake_horizontal_chart'
        mock_chart.assert_called_once()


# ============================================================================
# TESTS: QuestionAnalyzer - Text Questions
# ============================================================================

class TestQuestionAnalyzerText:
    """Tests para análisis de preguntas de texto."""
    
    @pytest.mark.django_db
    def test_analyze_text_no_responses(self, pregunta_text, encuesta):
        """Debe retornar estructura básica sin respuestas."""
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_text_question(pregunta_text, qs)
        
        assert result['total_respuestas'] == 0
        assert result['samples_texto'] == []
    
    @pytest.mark.django_db
    def test_analyze_text_with_responses(
        self, pregunta_text, encuesta, user
    ):
        """Debe analizar respuestas de texto y extraer muestras."""
        # Crear respuestas
        textos = [
            'Excelente servicio',
            'Muy buen producto',
            'Calidad superior',
            'Gran experiencia'
        ]
        
        for texto in textos:
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=pregunta_text,
                text_value=text
            )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_text_question(pregunta_text, qs)
        
        assert result['total_respuestas'] == 4
        assert len(result['samples_texto']) <= 5  # Máximo 5 muestras
        assert result['insight'] != ''
    
    @pytest.mark.django_db
    @patch('core.services.analysis_service.TextAnalyzer.analyze_text_responses')
    def test_analyze_text_with_keywords(
        self, mock_analyzer, pregunta_text, encuesta, user
    ):
        """Debe mostrar palabras clave en insight."""
        mock_analyzer.return_value = (
            [('excelente', 5), ('producto', 3), ('calidad', 2)],
            []
        )
        
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=pregunta_text,
            text_value='Test'
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_text_question(pregunta_text, qs)
        
        assert 'excelente' in result['insight']
    
    @pytest.mark.django_db
    @patch('core.services.analysis_service.TextAnalyzer.analyze_text_responses')
    def test_analyze_text_no_keywords(
        self, mock_analyzer, pregunta_text, encuesta, user
    ):
        """Debe mostrar mensaje de respuestas dispersas si no hay keywords."""
        mock_analyzer.return_value = ([], [])
        
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=pregunta_text,
            text_value='Test'
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = QuestionAnalyzer.analyze_text_question(pregunta_text, qs)
        
        assert 'dispersas' in result['insight']


# ============================================================================
# TESTS: NPSCalculator
# ============================================================================

class TestNPSCalculator:
    """Tests para NPSCalculator."""
    
    @pytest.mark.django_db
    def test_calculate_nps_no_pregunta(self, encuesta):
        """Debe retornar None si no hay pregunta."""
        qs = SurveyResponse.objects.filter(survey=survey)
        result = NPSCalculator.calculate_nps(None, qs)
        
        assert result['score'] is None
        assert result['breakdown_chart'] is None
    
    @pytest.mark.django_db
    def test_calculate_nps_no_responses(self, pregunta_scale, encuesta):
        """Debe retornar None si no hay respuestas."""
        qs = SurveyResponse.objects.filter(survey=survey)
        result = NPSCalculator.calculate_nps(pregunta_scale, qs)
        
        assert result['score'] is None
    
    @pytest.mark.django_db
    def test_calculate_nps_promotores_only(
        self, pregunta_scale, encuesta, user
    ):
        """Debe calcular NPS=100 si todos son promotores."""
        # Promotores: 9-10
        for valor in [9, 10, 9, 10]:
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=pregunta_scale,
                numeric_value=valor
            )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = NPSCalculator.calculate_nps(pregunta_scale, qs)
        
        assert result['score'] == 100.0
    
    @pytest.mark.django_db
    def test_calculate_nps_detractores_only(
        self, pregunta_scale, encuesta, user
    ):
        """Debe calcular NPS=-100 si todos son detractores."""
        # Detractores: 0-6
        for valor in [3, 4, 5, 6]:
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=pregunta_scale,
                numeric_value=valor
            )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = NPSCalculator.calculate_nps(pregunta_scale, qs)
        
        assert result['score'] == -100.0
    
    @pytest.mark.django_db
    def test_calculate_nps_mixed_responses(
        self, pregunta_scale, encuesta, user
    ):
        """Debe calcular NPS correctamente con respuestas mixtas."""
        # 5 promotores (9-10), 3 pasivos (7-8), 2 detractores (0-6)
        valores = [9, 10, 9, 10, 9, 7, 8, 7, 5, 6]
        
        for valor in valores:
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=pregunta_scale,
                numeric_value=valor
            )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = NPSCalculator.calculate_nps(pregunta_scale, qs)
        
        # NPS = (5/10 * 100) - (2/10 * 100) = 50 - 20 = 30
        assert result['score'] == 30.0
    
    @pytest.mark.django_db
    @patch('core.services.analysis_service.ChartGenerator.generate_nps_chart')
    def test_calculate_nps_generates_chart(
        self, mock_chart, pregunta_scale, encuesta, user
    ):
        """Debe generar gráfico si include_chart=True."""
        mock_chart.return_value = 'fake_nps_chart'
        
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=pregunta_scale,
            numeric_value=9
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = NPSCalculator.calculate_nps(pregunta_scale, qs, include_chart=True)
        
        assert result['breakdown_chart'] == 'fake_nps_chart'
        mock_chart.assert_called_once()
    
    @pytest.mark.django_db
    def test_calculate_nps_no_chart_if_disabled(
        self, pregunta_scale, encuesta, user
    ):
        """No debe generar gráfico si include_chart=False."""
        resp = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=resp,
            question=pregunta_scale,
            numeric_value=9
        )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = NPSCalculator.calculate_nps(pregunta_scale, qs, include_chart=False)
        
        assert result['breakdown_chart'] is None
    
    @pytest.mark.django_db
    def test_calculate_nps_pasivos_not_counted(
        self, pregunta_scale, encuesta, user
    ):
        """Los pasivos (7-8) no deben afectar el score de NPS."""
        # Solo pasivos
        for valor in [7, 8, 7, 8]:
            resp = SurveyResponse.objects.create(survey=survey, user=user)
            QuestionResponse.objects.create(
                survey_response=resp,
                question=pregunta_scale,
                numeric_value=valor
            )
        
        qs = SurveyResponse.objects.filter(survey=survey)
        result = NPSCalculator.calculate_nps(pregunta_scale, qs)
        
        # NPS = (0% promotores) - (0% detractores) = 0
        assert result['score'] == 0.0
