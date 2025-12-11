from django.db import models
from django.conf import settings
# Usamos una importación directa si surveys.models ya está cargado, 
# pero 'surveys.Survey' como string es más seguro para evitar ciclos en algunos contextos.
# Aquí importamos el modelo para tener validación fuerte de FK.
from surveys.models import Survey

class ScheduledReport(models.Model):
    """
    [Faltante Anteproyecto]: Programación de reportes automáticos.
    Permite configurar el envío periódico de PDFs a una lista de correos.
    """
    FREQUENCY_CHOICES = [
        ('daily', 'Diario'),
        ('weekly', 'Semanal'),
        ('monthly', 'Mensual'),
    ]

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, verbose_name="Encuesta")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Propietario")
    
    emails = models.TextField(
        help_text="Lista de correos destinatarios separados por coma",
        verbose_name="Destinatarios"
    )
    
    frequency = models.CharField(
        max_length=20, 
        choices=FREQUENCY_CHOICES,
        verbose_name="Frecuencia de Envío"
    )
    
    is_active = models.BooleanField(default=True, verbose_name="¿Activo?")
    last_sent_at = models.DateTimeField(null=True, blank=True, verbose_name="Última vez enviado")
    
    # Opciones de contenido para personalizar el reporte
    include_charts = models.BooleanField(default=True, verbose_name="Incluir Gráficos")
    include_raw_data = models.BooleanField(default=False, verbose_name="Incluir CSV Adjunto")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Reporte {self.get_frequency_display()} - {self.survey.title}"

    class Meta:
        verbose_name = "Reporte Programado"
        verbose_name_plural = "Reportes Programados"
        ordering = ['-created_at']