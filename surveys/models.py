"""surveys/models.py"""
from django.db import models
from django.db.models import Max
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError

class SurveyTemplate(models.Model):
    """
    [Faltante Anteproyecto]: Sistema de plantillas reutilizables.
    Permite instanciar nuevas encuestas basándose en diseños predefinidos.
    """
    title = models.CharField(max_length=255, verbose_name="Nombre de la Plantilla")
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, default='General')
    # JSONField para guardar la estructura de preguntas y opciones
    structure = models.JSONField(verbose_name="Estructura JSON", help_text="Definición de preguntas y lógica")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    def clean(self):
        """Valida que la estructura tenga el formato correcto"""
        super().clean()
        if not isinstance(self.structure, list):
            raise ValidationError({'structure': 'La estructura debe ser una lista de preguntas.'})
        # Opcional: Validar que cada pregunta tenga 'text' y 'type'
        for q in self.structure:
            if 'text' not in q or 'type' not in q:
                raise ValidationError({'structure': 'Cada pregunta en la estructura debe tener "text" y "type".'})

    # --- MÉTODO PARA INSTANCIAR ---
    def create_survey_instance(self, author):
        """
        Crea una nueva Survey funcional basada en esta plantilla.
        Copia preguntas y opciones desde el JSON 'structure'.
        """
        # 1. Crear la Encuesta Base
        new_survey = Survey.objects.create(
            title=f"Copia de {self.title}",
            description=self.description,
            category=self.category,
            status=Survey.STATUS_DRAFT,
            author=author
        )

        # 2. Recrear estructura desde el JSON
        if not self.structure:
            return new_survey

        for i, q_data in enumerate(self.structure):
            question = Question.objects.create(
                survey=new_survey,
                text=q_data.get('text', 'Pregunta sin título'),
                type=q_data.get('type', 'text'),
                order=i + 1,  # Siempre secuencial, empezando en 1
                is_required=q_data.get('required', False)
            )
            
            # Crear opciones si existen
            options_list = q_data.get('options', [])
            if options_list and isinstance(options_list, list):
                for j, opt_text in enumerate(options_list):
                    if opt_text.strip():
                        AnswerOption.objects.create(
                            question=question,
                            text=opt_text.strip(),
                            order=j
                        )
        
        return new_survey


class Survey(models.Model):
    """Survey model - Encuesta"""

    STATUS_DRAFT = 'draft'
    STATUS_ACTIVE = 'active'
    STATUS_PAUSED = 'paused'
    STATUS_CLOSED = 'closed'

    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Borrador'),
        (STATUS_ACTIVE, 'Activa'),
        (STATUS_PAUSED, 'En Pausa'),
        (STATUS_CLOSED, 'Cerrada'),
    ]

    ALLOWED_TRANSITIONS = {
        STATUS_DRAFT: {STATUS_DRAFT, STATUS_ACTIVE, STATUS_CLOSED},
        STATUS_ACTIVE: {STATUS_ACTIVE, STATUS_PAUSED, STATUS_CLOSED},
        STATUS_PAUSED: {STATUS_PAUSED, STATUS_ACTIVE, STATUS_CLOSED},
        STATUS_CLOSED: {STATUS_CLOSED},
    }

    title = models.CharField(max_length=255, verbose_name='Title')
    description = models.TextField(null=True, blank=True, verbose_name='Description')
    
    category = models.CharField(
        max_length=100,
        default='General',
        verbose_name='Category',
        db_index=True
    )
    
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        verbose_name='Status',
        db_index=True
    )
    author = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Author', db_index=True)
    author_sequence = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Author Sequence',
        db_index=True,
        help_text='Número incremental de la encuesta para el autor'
    )
    public_id = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        verbose_name='Public ID',
        db_index=True,
        help_text='Identificador legible mostrado en URLs'
    )
    sample_goal = models.PositiveIntegerField(default=0, verbose_name='Sample Goal')
    is_imported = models.BooleanField(
        default=False, 
        verbose_name='Is Imported',
        help_text='Indica si la encuesta fue importada desde CSV (no permite cambiar estado)'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created At', db_index=True)
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated At')

    def __str__(self):
        return self.title

    def get_allowed_status_transitions(self, from_status=None):
        current_status = from_status or self.status
        return self.ALLOWED_TRANSITIONS.get(current_status, {current_status})

    def validate_status_transition(self, new_status, *, from_status=None):
        valid_statuses = {code for code, _ in self.STATUS_CHOICES}
        if new_status not in valid_statuses:
            raise ValidationError(f"Estado inválido: {new_status}")
            
        if new_status == self.STATUS_ACTIVE:
            if hasattr(self.author, 'subscription') and self.author.subscription.is_valid():
                plan = self.author.subscription.plan
                active_surveys_count = Survey.objects.filter(
                    author=self.author,
                    status=self.STATUS_ACTIVE
                ).exclude(pk=self.pk).count()
                
                if active_surveys_count >= plan.max_surveys:
                    raise ValidationError(
                        f"Has alcanzado el límite de {plan.max_surveys} encuestas activas permitido por tu plan '{plan.name}'."
                    )

        if new_status not in self.get_allowed_status_transitions(from_status):
            raise ValidationError("La transición solicitada no está permitida.")
        return True

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Survey'
        verbose_name_plural = 'Surveys'
        db_table = 'surveys_survey'
        constraints = [
            models.UniqueConstraint(
                fields=['author', 'author_sequence'],
                name='survey_author_sequence_unique'
            )
        ]

    def _ensure_public_identifier(self):
        if not self.author_id:
            return

        if self.author_sequence is None:
            qs = self.__class__.objects.filter(author_id=self.author_id)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            max_seq = qs.aggregate(max_seq=Max('author_sequence')).get('max_seq') or 0
            self.author_sequence = max_seq + 1

        if not self.public_id:
            self.public_id = f"SUR-{self.author_id:03d}-{self.author_sequence:04d}"

    def save(self, *args, **kwargs):
        self._ensure_public_identifier()
        super().save(*args, **kwargs)


class Question(models.Model):
    """Question model - Pregunta"""
    
    TYPE_CHOICES = [
        ('text', 'Texto libre'),
        ('number', 'Número'),
        ('scale', 'Escala 1-10'),
        ('single', 'Opción única'),
        ('multi', 'Opción múltiple'),
    ]

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
    
    is_demographic = models.BooleanField(default=False, verbose_name='Is Demographic', db_index=True)
    demographic_type = models.CharField(max_length=50, choices=DEMOGRAPHIC_TYPES, null=True, blank=True, verbose_name='Demographic Type')
    
    is_analyzable = models.BooleanField(
        default=True, 
        verbose_name='Is Analyzable',
        help_text='Indica si esta pregunta debe incluirse en los reportes estadísticos automáticos'
    )

    depends_on = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='dependent_questions',
        verbose_name="Depende de la pregunta"
    )
    visible_if_option = models.ForeignKey(
        'AnswerOption',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Visible si selecciona",
        related_name="visible_in_questions"
    )

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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

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


class ImportJob(models.Model):
    """Modelo para rastrear el estado de una importación masiva de respuestas desde CSV."""
    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("processing", "Procesando"),
        ("completed", "Completado"),
        ("failed", "Fallido"),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Usuario")
    survey = models.ForeignKey(Survey, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Encuesta")
    csv_file = models.CharField(max_length=512, verbose_name="Ruta archivo CSV")
    original_filename = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Nombre original del archivo",
        help_text="Nombre del archivo CSV subido por el usuario"
    )
    survey_title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Título personalizado de la encuesta",
        help_text="Si está vacío, usa el nombre del archivo"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    total_rows = models.PositiveIntegerField(default=0)
    processed_rows = models.PositiveIntegerField(default=0)
    error_message = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"ImportJob {self.id} - {self.status} ({self.csv_file})"

    class Meta:
        verbose_name = "Importación de CSV"
        verbose_name_plural = "Importaciones de CSV"
        db_table = "surveys_importjob"


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