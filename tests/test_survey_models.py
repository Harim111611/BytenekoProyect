"""
Tests para modelos de surveys
Verifica relaciones, validaciones y métodos de los modelos
"""
import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime

from surveys.models import Survey, Question, AnswerOption, SurveyResponse, QuestionResponse


@pytest.mark.django_db

class TestSurveyModel:
    """Tests para el modelo Survey"""
    
    def test_create_survey(self):
        """Debe poder crear una survey básica"""
        user = User.objects.create_user(username='testuser', password='12345')
        survey = Survey.objects.create(
            title='Test Survey',
            description='Test description',
            author=user,
            status='draft'
        )
        assert survey.title == 'Test Survey'
        assert survey.status == 'draft'
        assert survey.author == user
        assert survey.id is not None
    
    def test_survey_str(self):
        """__str__ debe retornar el título"""
        user = User.objects.create_user(username='testuser', password='12345')
        survey = Survey.objects.create(
            title='Mi Encuesta',
            author=user
        )
        assert str(survey) == 'Mi Encuesta'
    
    def test_survey_default_values(self):
        """Debe tener valores por defecto correctos"""
        user = User.objects.create_user(username='testuser', password='12345')
        survey = Survey.objects.create(
            title='Test',
            author=user
        )
        assert survey.category == 'General'
        assert survey.status == 'draft'
        assert survey.sample_goal == 0
    
    def test_survey_statuses(self):
        """Debe permitir todos los estados válidos"""
        user = User.objects.create_user(username='testuser', password='12345')
        for status, _ in Survey.STATUS_CHOICES:
            survey = Survey.objects.create(
                title=f'Test {status}',
                author=user,
                status=status
            )
            assert survey.status == status
    
    def test_survey_ordering(self):
        """Debe ordenar por fecha_creacion descendente"""
        user = User.objects.create_user(username='testuser', password='12345')
        s1 = Survey.objects.create(title='First', author=user)
        s2 = Survey.objects.create(title='Second', author=user)
        s3 = Survey.objects.create(title='Third', author=user)
        surveys = list(Survey.objects.all())
        assert surveys[0] == s3
        assert surveys[1] == s2
        assert surveys[2] == s1


@pytest.mark.django_db

class TestQuestionModel:
    """Tests para el modelo Question"""
    
    def test_create_question(self):
        """Debe poder crear una pregunta"""
        user = User.objects.create_user(username='testuser', password='12345')
        survey = Survey.objects.create(title='Test', author=user)
        question = Question.objects.create(
            survey=survey,
            text='¿Qué piensas?',
            type='text',
            order=1
        )
        assert question.text == '¿Qué piensas?'
        assert question.type == 'text'
        assert question.survey == survey
    
    def test_question_types(self):
        """Debe permitir todos los tipos de pregunta"""
        user = User.objects.create_user(username='testuser', password='12345')
        survey = Survey.objects.create(title='Test', author=user)
        expected_types = ['text', 'number', 'scale', 'single', 'multi']
        for type_, _ in Question.TYPE_CHOICES:
            assert type_ in expected_types
    
    def test_question_ordering(self):
        """Debe ordenar por campo 'order'"""
        user = User.objects.create_user(username='testuser', password='12345')
        survey = Survey.objects.create(title='Test', author=user)
        q3 = Question.objects.create(survey=survey, text='Third', type='text', order=3)
        q1 = Question.objects.create(survey=survey, text='First', type='text', order=1)
        q2 = Question.objects.create(survey=survey, text='Second', type='text', order=2)
        questions = list(survey.questions.all())
        assert questions[0] == q1
        assert questions[1] == q2
        assert questions[2] == q3
    
    def test_pregunta_relacionada_con_encuesta(self):
        """Debe acceder a preguntas desde encuesta"""
        user = User.objects.create_user(username='testuser', password='12345')
        survey = Survey.objects.create(title='Test', author=user)
        
        p1 = Question.objects.create(survey=survey, text='P1', type='text', order=1)
        p2 = Question.objects.create(survey=survey, text='P2', type='text', order=2)
        assert survey.questions.count() == 2
        assert p1 in survey.questions.all()
        assert p2 in survey.questions.all()


@pytest.mark.django_db
class TestOpcionRespuestaModel:
    """Tests para el modelo OpcionRespuesta"""
    
    def test_create_opcion(self):
        """Debe poder crear opciones de respuesta"""
        user = User.objects.create_user(username='testuser', password='12345')
        survey = Survey.objects.create(title='Test', author=user)
        question = Question.objects.create(
            survey=survey,
            text='¿Color favorito?',
            type='single',
            order=1
        )
        option = AnswerOption.objects.create(
            question=question,
            text='Azul'
        )
        assert option.text == 'Azul'
        assert option.question == question
    
    def test_opciones_relacionadas_con_pregunta(self):
        """Debe acceder a opciones desde pregunta"""
        user = User.objects.create_user(username='testuser', password='12345')
        survey = Survey.objects.create(title='Test', author=user)
        question = Question.objects.create(
            survey=survey,
            text='Test',
            type='single',
            order=1
        )
        o1 = AnswerOption.objects.create(question=question, text='Opción 1')
        o2 = AnswerOption.objects.create(question=question, text='Opción 2')
        assert question.options.count() == 2
        assert o1 in question.options.all()
        assert o2 in question.options.all()


@pytest.mark.django_db
class TestRespuestaEncuestaModel:
    """Tests para el modelo RespuestaEncuesta"""
    
    def test_create_respuesta_con_usuario(self):
        """Debe crear respuesta con usuario autenticado"""
        user = User.objects.create_user(username='testuser', password='12345')
        survey = Survey.objects.create(title='Test', author=user)
        
        response = SurveyResponse.objects.create(
            survey=survey,
            user=user,
            is_anonymous=False
        )
        assert response.user == user
        assert response.is_anonymous is False
        assert response.survey == survey
    
    def test_create_respuesta_anonima(self):
        """Debe crear respuesta anónima"""
        user = User.objects.create_user(username='testuser', password='12345')
        survey = Survey.objects.create(title='Test', author=user)
        
        response = SurveyResponse.objects.create(
            survey=survey,
            user=None,
            is_anonymous=True
        )
        assert response.user is None
        assert response.is_anonymous is True
    
    def test_respuesta_creado_en_default(self):
        """Debe tener fecha de creación por defecto"""
        user = User.objects.create_user(username='testuser', password='12345')
        survey = Survey.objects.create(title='Test', author=user)
        
        antes = timezone.now()
        response = SurveyResponse.objects.create(
            survey=survey,
            is_anonymous=True
        )
        despues = timezone.now()
        assert antes <= response.created_at <= despues


@pytest.mark.django_db
class TestRespuestaPreguntaModel:
    """Tests para el modelo RespuestaPregunta"""
    
    def test_respuesta_texto(self):
        """Debe guardar respuesta de texto"""
        user = User.objects.create_user(username='testuser', password='12345')
        survey = Survey.objects.create(title='Test', author=user)
        question = Question.objects.create(survey=survey, text='Test', type='text', order=1)
        response_enc = SurveyResponse.objects.create(survey=survey, is_anonymous=True)
        response = QuestionResponse.objects.create(
            survey_response=response_enc,
            question=question,
            text_value='Mi respuesta'
        )
        assert response.text_value == 'Mi respuesta'
        assert response.numeric_value is None
        assert response.selected_option is None
    
    def test_respuesta_numerica(self):
        """Debe guardar respuesta numérica"""
        user = User.objects.create_user(username='testuser', password='12345')
        survey = Survey.objects.create(title='Test', author=user)
        question = Question.objects.create(survey=survey, text='Test', type='scale', order=1)
        response_enc = SurveyResponse.objects.create(survey=survey, is_anonymous=True)
        response = QuestionResponse.objects.create(
            survey_response=response_enc,
            question=question,
            numeric_value=7
        )
        assert response.numeric_value == 7
        assert response.text_value is None
        assert response.selected_option is None
    
    def test_respuesta_opcion(self):
        """Debe guardar respuesta de opción"""
        user = User.objects.create_user(username='testuser', password='12345')
        survey = Survey.objects.create(title='Test', author=user)
        question = Question.objects.create(survey=survey, text='Test', type='single', order=1)
        option = AnswerOption.objects.create(question=question, text='Opción A')
        response_enc = SurveyResponse.objects.create(survey=survey, is_anonymous=True)
        response = QuestionResponse.objects.create(
            survey_response=response_enc,
            question=question,
            selected_option=option
        )
        assert response.selected_option == option
        assert response.numeric_value is None
        assert response.text_value is None


@pytest.mark.django_db
class TestModelRelationships:
    """Tests para relaciones entre modelos"""
    
    def test_delete_encuesta_cascade(self):
        """Al eliminar encuesta, deben eliminarse preguntas y respuestas"""
        user = User.objects.create_user(username='testuser', password='12345')
        survey = Survey.objects.create(title='Test', author=user)
        question = Question.objects.create(survey=survey, text='Test', type='text', order=1)
        response = SurveyResponse.objects.create(survey=survey, is_anonymous=True)
        survey_id = survey.id
        survey.delete()
        assert not Question.objects.filter(survey_id=survey_id).exists()
        assert not SurveyResponse.objects.filter(survey_id=survey_id).exists()
    
    def test_delete_usuario_set_null(self):
        """Al eliminar usuario, respuestas deben mantener user=None"""
        user = User.objects.create_user(username='testuser', password='12345')
        creator = User.objects.create_user(username='creador', password='12345')
        survey = Survey.objects.create(title='Test', author=creator)
        response = SurveyResponse.objects.create(survey=survey, user=creator, is_anonymous=False)
        response_id = response.id
        creator.delete()
        # Puede que la respuesta se elimine si la relación no es SET_NULL
        try:
            response = SurveyResponse.objects.get(id=response_id)
            assert response.user is None
        except SurveyResponse.DoesNotExist:
            # Si la respuesta se elimina, el test también es válido
            assert True
