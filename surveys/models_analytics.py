from django.db import models
from django.conf import settings

class AnalysisSegment(models.Model):
    """
    [Faltante Anteproyecto]: Segmentación de clientes guardada.
    Permite guardar filtros (ej. 'Mujeres > 30 años') para reusarlos.
    """
    name = models.CharField(max_length=100, verbose_name="Nombre del Segmento")
    
    # Usamos referencia en string para evitar ciclos de importación con surveys.models
    survey = models.ForeignKey('surveys.Survey', on_delete=models.CASCADE, related_name='saved_segments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    # Guardar los criterios de filtro como JSON 
    # Ej. {question_1: "Opcion A", question_5_min: 30}
    filters_criteria = models.JSONField(verbose_name="Criterios de Filtro") 
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.survey}"

    class Meta:
        verbose_name = "Segmento de Análisis"
        verbose_name_plural = "Segmentos de Análisis"
        ordering = ['-created_at']