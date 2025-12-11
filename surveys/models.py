"""surveys/models.py"""
from django.db import models, transaction
from django.db.models import Max
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError

class SurveyTemplate(models.Model):
    """
    Sistema de plantillas reutilizables.
    Define la estructura base para instanciar encuestas repetitivas.
    """
    title = models.CharField(max_length=255, verbose_name="Nombre de la Plantilla")
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, default='General')
    structure = models.JSONField(verbose_name="Estructura JSON", help_text="Definición de preguntas y lógica")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    def clean(self):
        """Valida la integridad de la estructura JSON."""
        super().clean()
        if not isinstance(self.structure, list):
            raise ValidationError({'structure': 'La estructura debe ser una lista de objetos de pregunta.'})
        
        valid_types = [choice[0] for choice in Question.TYPE_CHOICES]
        
        for index, q in enumerate(self.structure):
            if 'text' not in q or 'type' not in q:
                raise ValidationError({'structure': f'La pregunta en índice {index} debe tener "text" y "type".'})
            
            if q['type'] not in valid_types:
                raise ValidationError({'structure': f'Tipo de pregunta inválido "{q["type"]}" en índice {index}.'})
            
            # Validar opciones para tipos que las requieren
            if q['type'] in ['single', 'multi']:
                options = q.get('options', [])
                if not options or not isinstance(options, list) or len(options) < 1:
                    raise ValidationError({'structure': f'La pregunta "{q["text"]}" de tipo {q["type"]} debe tener una lista de "options".'})

    def create_survey_instance(self, author):
        """
        Crea una nueva Survey funcional basada en esta plantilla de forma atómica.
        """
        with transaction.atomic():
            new_survey = Survey.objects.create(
                title=f"Copia de {self.title}",
                description=self.description,
                category=self.category,
                status=Survey.STATUS_DRAFT,
                author=author
            )

            if not self.structure:
                return new_survey

            for i, q_data in enumerate(self.structure):
                question = Question.objects.create(
                    survey=new_survey,
                    text=q_data.get('text', 'Pregunta sin título'),
                    type=q_data.get('type', 'text'),
                    order=i + 1,
                    is_required=q_data.get('required', False)
                )
                
                options_list = q_data.get('options', [])
                if options_list and isinstance(options_list, list):
                    option_objs = [
                        AnswerOption(question=question, text=opt_text.strip(), order=j)
                        for j, opt_text in enumerate(options_list)
                        if opt_text.strip()
                    ]
                    AnswerOption.objects.bulk_create(option_objs)
            
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
    category = models.CharField(max_length=100, default='General', verbose_name='Category', db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT, verbose_name='Status', db_index=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Author', db_index=True)
    author_sequence = models.PositiveIntegerField(null=True, blank=True, verbose_name='Author Sequence', db_index=True)
    public_id = models.CharField(max_length=20, unique=True, null=True, blank=True, verbose_name='Public ID', db_index=True)
    sample_goal = models.PositiveIntegerField(default=0, verbose_name='Sample Goal')
    is_imported = models.BooleanField(default=False, verbose_name='Is Imported', help_text='Indica si la encuesta fue importada desde CSV.')
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
            # Validación de límites de suscripción (Simplificada para robustez)
            if hasattr(self.author, 'subscription') and self.author.subscription.is_valid():
                plan = self.author.subscription.plan
                active_count = Survey.objects.filter(author=self.author, status=self.STATUS_ACTIVE).exclude(pk=self.pk).count()
                if active_count >= plan.max_surveys:
                    raise ValidationError(f"Límite de encuestas activas ({plan.max_surveys}) alcanzado.")

        current = from_status or self.status
        if new_status not in self.get_allowed_status_transitions(current):
            raise ValidationError(f"Transición no permitida de {current} a {new_status}.")
        return True

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Survey'
        verbose_name_plural = 'Surveys'
        db_table = 'surveys_survey'
        constraints = [
            models.UniqueConstraint(fields=['author', 'author_sequence'], name='survey_author_sequence_unique')
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
    """Question model"""
    TYPE_CHOICES = [
        ('text', 'Texto libre'),
        ('number', 'Número'),
        ('scale', 'Escala 1-10'),
        ('single', 'Opción única'),
        ('multi', 'Opción múltiple'),
    ]
    DEMOGRAPHIC_TYPES = [
        ('age', 'Edad'), ('gender', 'Género'), ('location', 'Ubicación'),
        ('occupation', 'Ocupación'), ('marital_status', 'Estado civil'), ('other', 'Otro'),
    ]

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='questions', verbose_name='Survey', db_index=True)
    text = models.CharField(max_length=500, verbose_name='Question Text')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name='Type', db_index=True)
    is_required = models.BooleanField(default=False, verbose_name='Required')
    order = models.PositiveIntegerField(default=0, verbose_name='Order')
    
    is_demographic = models.BooleanField(default=False, verbose_name='Is Demographic', db_index=True)
    demographic_type = models.CharField(max_length=50, choices=DEMOGRAPHIC_TYPES, null=True, blank=True)
    is_analyzable = models.BooleanField(default=True, verbose_name='Is Analyzable')

    depends_on = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='dependent_questions')
    visible_if_option = models.ForeignKey('AnswerOption', on_delete=models.SET_NULL, null=True, blank=True, related_name="visible_in_questions")

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
    """Answer option"""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.text

    class Meta:
        ordering = ['order']
        verbose_name = 'Answer Option'
        verbose_name_plural = 'Answer Options'
        db_table = 'surveys_answeroption'
        indexes = [models.Index(fields=['question'], name='answeroption_question_idx')]


class SurveyResponse(models.Model):
    """Survey response submission"""
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='responses', db_index=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    is_anonymous = models.BooleanField(default=False)

    def __str__(self):
        return f"Respuesta a {self.survey.title} ({self.created_at})"

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
    """Rastreo de importación masiva."""
    STATUS_CHOICES = [("pending", "Pendiente"), ("processing", "Procesando"), ("completed", "Completado"), ("failed", "Fallido")]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    survey = models.ForeignKey(Survey, on_delete=models.SET_NULL, null=True, blank=True)
    # Se recomienda FileField en producción, pero CharField soporta la lógica actual de bulk_import
    csv_file = models.CharField(max_length=512, verbose_name="Ruta archivo CSV")
    original_filename = models.CharField(max_length=255, blank=True, null=True)
    survey_title = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    total_rows = models.PositiveIntegerField(default=0)
    processed_rows = models.PositiveIntegerField(default=0)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Importación de CSV"
        verbose_name_plural = "Importaciones de CSV"
        db_table = "surveys_importjob"


class QuestionResponse(models.Model):
    """Individual question response"""
    survey_response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE, related_name='question_responses', db_index=True)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, db_index=True)
    selected_option = models.ForeignKey(AnswerOption, on_delete=models.SET_NULL, null=True, blank=True)
    text_value = models.TextField(null=True, blank=True)
    numeric_value = models.IntegerField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = 'Question Response'
        verbose_name_plural = 'Question Responses'
        db_table = 'surveys_questionresponse'
        indexes = [
            models.Index(fields=['survey_response', 'question'], name='qresponse_survey_q_idx'),
            models.Index(fields=['question', 'numeric_value'], name='qresponse_q_numeric_idx'),
            models.Index(fields=['question', 'selected_option'], name='qresponse_q_option_idx'),
        ]