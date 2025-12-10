# Exported function for external use
from .pptx_generator import PPTXReportGenerator

def generate_full_pptx_report(survey, analysis_data, nps_data=None, **kwargs):
    """
    Genera un reporte PPTX completo a partir de los datos de análisis y encuesta.
    Args:
        survey: Objeto encuesta (debe tener al menos .title)
        analysis_data: Lista de análisis de preguntas
        nps_data: Diccionario de datos NPS (opcional)
        kwargs: Otros parámetros opcionales (start_date, end_date, total_responses, kpi_satisfaction_avg, heatmap_image)
    Returns:
        bytes: Archivo PPTX en binario
    """
    generator = PPTXReportGenerator()
    return generator.generate(survey, analysis_data, nps_data, **kwargs)
