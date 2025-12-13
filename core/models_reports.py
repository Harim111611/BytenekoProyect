# core/models_reports.py
import os
from django.db import models
from django.conf import settings
from django.utils import timezone

# Asumimos que Survey está correctamente referenciado usando una AppConfig o está en el path
# En este caso, lo referenciamos por string para evitar circular imports si Surveys
# también está en models.py
SURVEY_MODEL = 'surveys.Survey'
USER_MODEL = settings.AUTH_USER_MODEL

class ReportJob(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pendiente'),
        ('PROCESSING', 'Procesando'),
        ('COMPLETED', 'Completado'),
        ('FAILED', 'Fallido'),
    ]
    REPORT_TYPES = [
        ('PDF', 'PDF'),
        ('PPTX', 'PowerPoint'),
    ]

    # Relaciones
    user = models.ForeignKey(USER_MODEL, on_delete=models.CASCADE, related_name='report_jobs')
    survey = models.ForeignKey(SURVEY_MODEL, on_delete=models.CASCADE, related_name='report_jobs')

    # Metadatos del Job
    report_type = models.CharField(max_length=10, choices=REPORT_TYPES, default='PDF')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    metadata = models.JSONField(default=dict, blank=True) # Para guardar filtros, etc.

    # Rastreabilidad del archivo
    file_path = models.CharField(max_length=255, blank=True, null=True, help_text="Ruta local del archivo")
    file_url = models.URLField(max_length=255, blank=True, null=True, help_text="URL pública para descarga")

    # Tiempos
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Report {self.id} for {self.survey.title} ({self.get_status_display()})"

    @property
    def is_finished(self):
        return self.status in ['COMPLETED', 'FAILED']
        
    def get_download_url(self):
        if self.file_url:
            return self.file_url
        return '#'