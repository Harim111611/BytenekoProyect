"""
surveys/models.py
Modelos principales para encuestas y respuestas.
"""
import uuid
import secrets
from django.db import models, transaction
from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError

class Question(models.Model):
    """
    Modelo de Pregunta. Definido antes para ser usado en SurveyTemplate.
    """
    TYPE_CHOICES = [
        ('text', 'Texto Corto'),
        ('textarea', 'Texto Largo'),
        ('number', 'Número'),
        ('single', 'Selección Única (Radio)'),
        ('multi', 'Selección Múltiple (Checkbox)'),
        ('select', 'Lista Desplegable'),
        ('scale', 'Escala (1-10 o 1-5)'),
        ('date', 'Fecha'),
        ('section', 'Sección / Encabezado'),
    ]

    # ForeignKey 'Survey' se define como string para evitar error de definición circular
    survey = models.ForeignKey('Survey', on_delete=models.CASCADE, related_name='questions')
    text = models.TextField(verbose_name="Pregunta")
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='text')
    required = models.BooleanField(default=False, verbose_name="Obligatoria")
    order = models.PositiveIntegerField(default=0)
    
    # Configuración JSON para flexibilidad (ej. rango de escala, placeholders)
    config = models.JSONField(default=dict, blank=True)
    
    # Flags para análisis inteligente
    is_analyzable = models.BooleanField(default=True, help_text="Incluir en reportes automáticos")
    is_demographic = models.BooleanField(default=False, help_text="Es dato demográfico (Edad, Género, etc.)")

    class Meta:
        ordering = ['order']
        indexes = [
            models.Index(fields=['survey', 'order']),
        ]

    def __str__(self):
        return f"{self.text[:50]} ({self.get_type_display()})"

class AnswerOption(models.Model):
    """Opciones para preguntas de selección (single, multi, select)."""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)
    value = models.CharField(max_length=50, blank=True, help_text="Valor interno para análisis (opcional)")

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.text

class Survey(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Borrador'),
        ('active', 'Activa'),
        ('closed', 'Cerrada'),
        ('paused', 'Pausada'),
    ]
    
    # Constantes para uso en código
    STATUS_DRAFT = 'draft'
    STATUS_ACTIVE = 'active'
    STATUS_PAUSED = 'paused'
    STATUS_CLOSED = 'closed'

    title = models.CharField(max_length=200, verbose_name="Título")
    description = models.TextField(blank=True, verbose_name="Descripción")
    
    # REFERENCIA AL USUARIO USANDO LA CONFIGURACIÓN (Evita Circular Import)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='surveys')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    
    # Identificador público seguro
    public_id = models.CharField(max_length=12, unique=True, editable=False, null=True)
    
    # Metadatos para análisis
    category = models.CharField(max_length=50, blank=True, null=True, verbose_name="Categoría (Ej. HR, CX)")
    sample_goal = models.IntegerField(default=0, verbose_name="Meta de Respuestas", help_text="0 = Sin límite")
    
    # Flag para distinguir encuestas importadas
    is_imported = models.BooleanField(default=False, verbose_name="Es Importada")

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['author', 'status']),
            models.Index(fields=['public_id']),
        ]

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = secrets.token_urlsafe(8)[:12]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

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
                    required=q_data.get('required', False)
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

class SurveyResponse(models.Model):
    """Una respuesta completa de un usuario a una encuesta."""
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='responses')
    
    # REFERENCIA AL USUARIO USANDO LA CONFIGURACIÓN
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='survey_responses')
    
    session_id = models.CharField(max_length=100, blank=True, null=True) # Para anónimos
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Estado de la respuesta
    is_complete = models.BooleanField(default=True)
    completion_time_seconds = models.PositiveIntegerField(null=True, blank=True)
    is_anonymous = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['survey', 'created_at']), # Crucial para filtros de fecha
        ]

    def __str__(self):
        return f"Resp: {self.survey.title} ({self.created_at.strftime('%d/%m %H:%M')})"

class QuestionResponse(models.Model):
    """La respuesta específica a una pregunta dentro de una SurveyResponse."""
    survey_response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE, related_name='question_responses')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='question_responses')
    
    # Almacenamiento polimórfico simple
    text_value = models.TextField(blank=True, null=True)
    numeric_value = models.FloatField(blank=True, null=True)
    
    selected_option = models.ForeignKey(AnswerOption, on_delete=models.SET_NULL, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            # Indices optimizados para análisis
            models.Index(fields=['question', 'numeric_value']), 
            models.Index(fields=['question', 'selected_option']),
            models.Index(fields=['survey_response', 'question']),
        ]

    def __str__(self):
        return f"Ans: {self.question.id} -> {self.text_value or self.numeric_value or self.selected_option}"

class ImportJob(models.Model):
    """Registro de tareas de importación masiva."""
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('processing', 'Procesando'),
        ('completed', 'Completado'),
        ('failed', 'Fallido'),
    ]
    
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='imports', null=True, blank=True)
    survey_title = models.CharField(max_length=200, blank=True) # Backup si se borra la survey
    csv_file = models.FileField(upload_to='imports/csv/', blank=True, null=True)
    original_filename = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    total_rows = models.IntegerField(default=0)
    processed_rows = models.IntegerField(default=0)
    error_log = models.TextField(blank=True)
    
    # REFERENCIA AL USUARIO USANDO LA CONFIGURACIÓN
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return f"Import {self.id} ({self.get_status_display()})"