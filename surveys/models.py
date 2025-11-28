# surveys/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Survey(models.Model):
    """Survey model - Encuesta"""
    
    STATUS_CHOICES = [
        ('draft', 'Borrador'),
        ('active', 'Activa'),
        ('closed', 'Cerrada'),
    ]

    title = models.CharField(max_length=255, verbose_name='Title')
    description = models.TextField(null=True, blank=True, verbose_name='Description')
    
    # Open field to store category from Select or "Other" input
    category = models.CharField(
        max_length=100,
        default='General',
        verbose_name='Category',
        db_index=True
    )
    
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='draft',
        verbose_name='Status',
        db_index=True
    )
    author = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Author', db_index=True)
    sample_goal = models.PositiveIntegerField(default=0, verbose_name='Sample Goal')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created At', db_index=True)
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated At')

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Survey'
        verbose_name_plural = 'Surveys'
        db_table = 'surveys_survey'


class Question(models.Model):
    """Question model - Pregunta"""
    
    TYPE_CHOICES = [
        ('text', 'Texto libre'),
        ('number', 'Número'),
        ('scale', 'Escala 1-10'),
        ('single', 'Opción única'),
        ('multi', 'Opción múltiple'),
    ]

    # Tipos demográficos (si la pregunta se usa para segmentación demográfica)
    DEMOGRAPHIC_TYPES = [
        ('age', 'Edad'),
        ('gender', 'Género'),
        ('location', 'Ubicación'),
        ('occupation', 'Ocupación'),
        ('marital_status', 'Estado civil'),
        ('other', 'Otro'),
    ]

    survey = models.ForeignKey(
        Survey,
        on_delete=models.CASCADE,
        related_name='questions',
        verbose_name='Survey',
        db_index=True
    )
    text = models.CharField(max_length=500, verbose_name='Question Text')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name='Type', db_index=True)
    is_required = models.BooleanField(default=False, verbose_name='Required')
    order = models.PositiveIntegerField(default=0, verbose_name='Order')
    # Marca si la pregunta es demográfica y su tipo (opcional)
    is_demographic = models.BooleanField(default=False, verbose_name='Is Demographic', db_index=True)
    demographic_type = models.CharField(max_length=50, choices=DEMOGRAPHIC_TYPES, null=True, blank=True, verbose_name='Demographic Type')

    def __str__(self):
        return self.text

    class Meta:
        ordering = ['order']
        verbose_name = 'Question'
        verbose_name_plural = 'Questions'
        db_table = 'surveys_question'
        indexes = [
            models.Index(fields=['survey', 'order'], name='survey_question_order_idx'),
            models.Index(fields=['survey', 'type'], name='survey_question_type_idx'),
        ]


class AnswerOption(models.Model):
    """Answer option for single/multiple choice questions - Opción de Respuesta"""
    
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='options',
        verbose_name='Question'
    )
    text = models.CharField(max_length=255, verbose_name='Option Text')
    order = models.PositiveIntegerField(default=0, verbose_name='Order')

    def __str__(self):
        return self.text

    class Meta:
        ordering = ['order']
        verbose_name = 'Answer Option'
        verbose_name_plural = 'Answer Options'
        db_table = 'surveys_answeroption'
        indexes = [
            models.Index(fields=['question'], name='answeroption_question_idx'),
        ]

class SurveyResponse(models.Model):
    """Survey response submission - Respuesta a Encuesta"""
    
    survey = models.ForeignKey(
        Survey,
        on_delete=models.CASCADE,
        related_name='responses',
        verbose_name='Survey',
        db_index=True
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='User',
        db_index=True
    )
    created_at = models.DateTimeField(default=timezone.now, verbose_name='Created At', db_index=True)
    is_anonymous = models.BooleanField(default=False, verbose_name='Anonymous')

    def __str__(self):
        return f"Respuesta a {self.survey.title} en {self.created_at.strftime('%Y-%m-%d')}"

    class Meta:
        verbose_name = 'Survey Response'
        verbose_name_plural = 'Survey Responses'
        db_table = 'surveys_surveyresponse'
        indexes = [
            models.Index(fields=['survey', 'created_at'], name='survey_response_date_idx'),
            models.Index(fields=['survey', 'is_anonymous'], name='survey_response_anon_idx'),
            models.Index(fields=['user', 'created_at'], name='user_response_date_idx'),
        ]
class QuestionResponse(models.Model):
    """Individual question response - Respuesta a Pregunta"""
    
    survey_response = models.ForeignKey(
        SurveyResponse,
        on_delete=models.CASCADE,
        related_name='question_responses',
        verbose_name='Survey Response',
        db_index=True
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE, verbose_name='Question', db_index=True)
    selected_option = models.ForeignKey(
        AnswerOption,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Selected Option'
    )
    text_value = models.TextField(null=True, blank=True, verbose_name='Text Value')
    numeric_value = models.IntegerField(null=True, blank=True, verbose_name='Numeric Value', db_index=True)

    def __str__(self):
        return f"Respuesta a: {self.question.text[:30]}..."

    class Meta:
        verbose_name = 'Question Response'
        verbose_name_plural = 'Question Responses'
        db_table = 'surveys_questionresponse'
        indexes = [
            models.Index(fields=['survey_response', 'question'], name='qresponse_survey_q_idx'),
            models.Index(fields=['question', 'numeric_value'], name='qresponse_q_numeric_idx'),
            models.Index(fields=['question', 'selected_option'], name='qresponse_q_option_idx'),
        ]


# Legacy model aliases for backward compatibility during migration
Encuesta = Survey
Pregunta = Question
OpcionRespuesta = AnswerOption
RespuestaEncuesta = SurveyResponse
RespuestaPregunta = QuestionResponse