"""
Tests para modelos de surveys
Verifica relaciones, validaciones y métodos de los modelos
"""
import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime

from surveys.models import (
    Encuesta,
    Pregunta,
    OpcionRespuesta,
    RespuestaEncuesta,
    RespuestaPregunta
)


@pytest.mark.django_db
class TestEncuestaModel:
    """Tests para el modelo Encuesta"""
    
    def test_create_encuesta(self):
        """Debe poder crear una encuesta básica"""
        user = User.objects.create_user(username='testuser', password='12345')
        encuesta = Survey.objects.create(
            title='Test Survey',
            description='Test description',
            author=user,
            status='draft'
        )
        
        assert encuesta.title == 'Test Survey'
        assert encuesta.status == 'draft'
        assert encuesta.author == user
        assert encuesta.id is not None
    
    def test_encuesta_str(self):
        """__str__ debe retornar el título"""
        user = User.objects.create_user(username='testuser', password='12345')
        encuesta = Survey.objects.create(
            title='Mi Encuesta',
            author=user
        )
        
        assert str(encuesta) == 'Mi Encuesta'
    
    def test_encuesta_default_values(self):
        """Debe tener valores por defecto correctos"""
        user = User.objects.create_user(username='testuser', password='12345')
        encuesta = Survey.objects.create(
            title='Test',
            author=user
        )
        
        assert encuesta.category == 'General'
        assert encuesta.status == 'draft'
        assert encuesta.sample_goal == 0
    
    def test_encuesta_estados(self):
        """Debe permitir todos los estados válidos"""
        user = User.objects.create_user(username='testuser', password='12345')
        
        for estado, _ in Encuesta.STATUS_CHOICES:
            encuesta = Survey.objects.create(
                title=f'Test {estado}',
                author=user,
                status=status
            )
            assert encuesta.status == estado
    
    def test_encuesta_ordering(self):
        """Debe ordenar por fecha_creacion descendente"""
        user = User.objects.create_user(username='testuser', password='12345')
        
        e1 = Survey.objects.create(title='First', author=user)
        e2 = Survey.objects.create(title='Second', author=user)
        e3 = Survey.objects.create(title='Third', author=user)
        
        encuestas = list(Survey.objects.all())
        assert encuestas[0] == e3
        assert encuestas[1] == e2
        assert encuestas[2] == e1


@pytest.mark.django_db
class TestPreguntaModel:
    """Tests para el modelo Pregunta"""
    
    def test_create_pregunta(self):
        """Debe poder crear una pregunta"""
        user = User.objects.create_user(username='testuser', password='12345')
        encuesta = Survey.objects.create(title='Test', author=user)
        
        pregunta = Question.objects.create(
            survey=survey,
            text='¿Qué piensas?',
            type='text',
            order=1
        )
        
        assert pregunta.text == '¿Qué piensas?'
        assert pregunta.type == 'text'
        assert pregunta.survey == encuesta
    
    def test_pregunta_tipos(self):
        """Debe permitir todos los tipos de pregunta"""
        user = User.objects.create_user(username='testuser', password='12345')
        encuesta = Survey.objects.create(title='Test', author=user)
        
        tipos_esperados = ['text', 'number', 'scale', 'single', 'multi']
        for tipo, _ in Pregunta.TYPE_CHOICES:
            assert tipo in tipos_esperados
    
    def test_pregunta_ordering(self):
        """Debe ordenar por campo 'orden'"""
        user = User.objects.create_user(username='testuser', password='12345')
        encuesta = Survey.objects.create(title='Test', author=user)
        
        p3 = Question.objects.create(survey=survey, text='Third', type='text', order=3)
        p1 = Question.objects.create(survey=survey, text='First', type='text', order=1)
        p2 = Question.objects.create(survey=survey, text='Second', type='text', order=2)
        
        preguntas = list(encuesta.questions.all())
        assert preguntas[0] == p1
        assert preguntas[1] == p2
        assert preguntas[2] == p3
    
    def test_pregunta_relacionada_con_encuesta(self):
        """Debe acceder a preguntas desde encuesta"""
        user = User.objects.create_user(username='testuser', password='12345')
        encuesta = Survey.objects.create(title='Test', author=user)
        
        p1 = Question.objects.create(survey=survey, text='P1', type='text', order=1)
        p2 = Question.objects.create(survey=survey, text='P2', type='text', order=2)
        
        assert encuesta.questions.count() == 2
        assert p1 in encuesta.questions.all()
        assert p2 in encuesta.questions.all()


@pytest.mark.django_db
class TestOpcionRespuestaModel:
    """Tests para el modelo OpcionRespuesta"""
    
    def test_create_opcion(self):
        """Debe poder crear opciones de respuesta"""
        user = User.objects.create_user(username='testuser', password='12345')
        encuesta = Survey.objects.create(title='Test', author=user)
        pregunta = Question.objects.create(
            survey=survey,
            text='¿Color favorito?',
            type='single',
            order=1
        )
        
        opcion = AnswerOption.objects.create(
            question=question,
            text='Azul'
        )
        
        assert opcion.text == 'Azul'
        assert opcion.question == pregunta
    
    def test_opciones_relacionadas_con_pregunta(self):
        """Debe acceder a opciones desde pregunta"""
        user = User.objects.create_user(username='testuser', password='12345')
        encuesta = Survey.objects.create(title='Test', author=user)
        pregunta = Question.objects.create(
            survey=survey,
            text='Test',
            type='single',
            order=1
        )
        
        o1 = AnswerOption.objects.create(question=question, text='Opción 1')
        o2 = AnswerOption.objects.create(question=question, text='Opción 2')
        
        assert pregunta.options.count() == 2
        assert o1 in pregunta.options.all()
        assert o2 in pregunta.options.all()


@pytest.mark.django_db
class TestRespuestaEncuestaModel:
    """Tests para el modelo RespuestaEncuesta"""
    
    def test_create_respuesta_con_usuario(self):
        """Debe crear respuesta con usuario autenticado"""
        user = User.objects.create_user(username='testuser', password='12345')
        encuesta = Survey.objects.create(title='Test', author=user)
        
        respuesta = SurveyResponse.objects.create(
            survey=survey,
            user=user,
            is_anonymous=False
        )
        
        assert respuesta.user == user
        assert respuesta.is_anonymous is False
        assert respuesta.survey == encuesta
    
    def test_create_respuesta_anonima(self):
        """Debe crear respuesta anónima"""
        user = User.objects.create_user(username='testuser', password='12345')
        encuesta = Survey.objects.create(title='Test', author=user)
        
        respuesta = SurveyResponse.objects.create(
            survey=survey,
            user=None,
            is_anonymous=True
        )
        
        assert respuesta.user is None
        assert respuesta.is_anonymous is True
    
    def test_respuesta_creado_en_default(self):
        """Debe tener fecha de creación por defecto"""
        user = User.objects.create_user(username='testuser', password='12345')
        encuesta = Survey.objects.create(title='Test', author=user)
        
        antes = timezone.now()
        respuesta = SurveyResponse.objects.create(
            survey=survey,
            is_anonymous=True
        )
        despues = timezone.now()
        
        assert antes <= respuesta.created_at <= despues


@pytest.mark.django_db
class TestRespuestaPreguntaModel:
    """Tests para el modelo RespuestaPregunta"""
    
    def test_respuesta_texto(self):
        """Debe guardar respuesta de texto"""
        user = User.objects.create_user(username='testuser', password='12345')
        encuesta = Survey.objects.create(title='Test', author=user)
        pregunta = Question.objects.create(survey=survey, text='Test', type='text', order=1)
        respuesta_enc = SurveyResponse.objects.create(survey=survey, is_anonymous=True)
        
        respuesta = QuestionResponse.objects.create(
            survey_response=respuesta_enc,
            question=question,
            text_value='Mi respuesta'
        )
        
        assert respuesta.text_value == 'Mi respuesta'
        assert respuesta.numeric_value is None
        assert respuesta.selected_option is None
    
    def test_respuesta_numerica(self):
        """Debe guardar respuesta numérica"""
        user = User.objects.create_user(username='testuser', password='12345')
        encuesta = Survey.objects.create(title='Test', author=user)
        pregunta = Question.objects.create(survey=survey, text='Test', type='scale', order=1)
        respuesta_enc = SurveyResponse.objects.create(survey=survey, is_anonymous=True)
        
        respuesta = QuestionResponse.objects.create(
            survey_response=respuesta_enc,
            question=question,
            numeric_value=7
        )
        
        assert respuesta.numeric_value == 7
        assert respuesta.text_value is None
        assert respuesta.selected_option is None
    
    def test_respuesta_opcion(self):
        """Debe guardar respuesta de opción"""
        user = User.objects.create_user(username='testuser', password='12345')
        encuesta = Survey.objects.create(title='Test', author=user)
        pregunta = Question.objects.create(survey=survey, text='Test', type='single', order=1)
        opcion = AnswerOption.objects.create(question=question, text='Opción A')
        respuesta_enc = SurveyResponse.objects.create(survey=survey, is_anonymous=True)
        
        respuesta = QuestionResponse.objects.create(
            survey_response=respuesta_enc,
            question=question,
            selected_option=selected_option
        )
        
        assert respuesta.selected_option == opcion
        assert respuesta.numeric_value is None
        assert respuesta.text_value is None


@pytest.mark.django_db
class TestModelRelationships:
    """Tests para relaciones entre modelos"""
    
    def test_delete_encuesta_cascade(self):
        """Al eliminar encuesta, deben eliminarse preguntas y respuestas"""
        user = User.objects.create_user(username='testuser', password='12345')
        encuesta = Survey.objects.create(title='Test', author=user)
        pregunta = Question.objects.create(survey=survey, text='Test', type='text', order=1)
        respuesta = SurveyResponse.objects.create(survey=survey, is_anonymous=True)
        
        encuesta_id = encuesta.id
        encuesta.delete()
        
        assert not Question.objects.filter(encuesta_id=encuesta_id).exists()
        assert not SurveyResponse.objects.filter(encuesta_id=encuesta_id).exists()
    
    def test_delete_usuario_set_null(self):
        """Al eliminar usuario, respuestas deben mantener user=None"""
        user = User.objects.create_user(username='testuser', password='12345')
        creador = User.objects.create_user(username='creador', password='12345')
        encuesta = Survey.objects.create(title='Test', author=author)
        respuesta = SurveyResponse.objects.create(survey=survey, user=user, is_anonymous=False)
        
        respuesta_id = respuesta.id
        user.delete()
        
        respuesta = SurveyResponse.objects.get(id=respuesta_id)
        assert respuesta.user is None
