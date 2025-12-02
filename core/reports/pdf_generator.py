"""
PDF Report Generator using WeasyPrint.
Generador profesional de reportes en formato PDF con diseño corporativo.
Version: 2.0 - Professional Edition
"""
import re
from datetime import datetime
from django.template.loader import render_to_string

try:
    from weasyprint import HTML
except ImportError:
    HTML = None


class PDFReportGenerator:
    """Generador profesional de reportes PDF con diseño moderno y limpio."""
    
    @staticmethod
    def generate_report(survey, analysis_data, nps_data, start_date=None, 
                       end_date=None, total_responses=0, include_table=False,
                       kpi_satisfaction_avg=0, request=None, **kwargs):
        """
        Genera un reporte PDF profesional para una encuesta.
        
        Args:
            survey: Objeto Survey
            analysis_data: Datos de análisis por pregunta
            nps_data: Datos de NPS (score, promoters, detractors, passives)
            start_date: Fecha de inicio del periodo
            end_date: Fecha de fin del periodo
            total_responses: Total de respuestas
            include_table: Incluir tablas de frecuencia
            kpi_satisfaction_avg: Promedio de satisfacción
            request: Request object para URLs absolutas
        
        Returns:
            bytes: Archivo PDF generado
        """
        if not HTML:
            raise ValueError("WeasyPrint no está instalado. Ejecute: pip install weasyprint")
        
        # Preparar contexto para el template
        context = {
            'survey': survey,
            'start_date': start_date,
            'end_date': end_date,
            'total_respuestas': total_responses, 
            'analysis_data': analysis_data,
            'nps_score': nps_data.get('score'),
            'nps_promoters': nps_data.get('promoters', 0),
            'nps_passives': nps_data.get('passives', 0),
            'nps_detractors': nps_data.get('detractors', 0),
            'kpi_prom_satisfaccion': kpi_satisfaction_avg, 
            'include_table': include_table,
            'fecha_generacion': datetime.now(),
        }
        
        # Renderizar HTML desde template
        html_string = render_to_string('core/report_pdf_template.html', context)
        
        # Obtener base URL para recursos estáticos
        base_url = request.build_absolute_uri('/') if request else None
        
        try:
            pdf_file = HTML(string=html_string, base_url=base_url).write_pdf()
            return pdf_file
        except Exception as e:
            raise ValueError(f"Error al generar PDF: {str(e)}")
    
    @staticmethod
    def get_filename(survey):
        """
        Genera un nombre de archivo limpio y descriptivo para el PDF.
        
        Args:
            survey: Objeto Survey
            
        Returns:
            str: Nombre de archivo sanitizado
        """
        # Limpiar título (solo alfanuméricos, espacios y guiones)
        clean_title = re.sub(r'[^\w\s-]', '', survey.title[:30])
        clean_title = re.sub(r'\s+', '_', clean_title.strip())
        
        # Fecha actual
        date_str = datetime.now().strftime('%Y%m%d_%H%M')
        
        # ID público si existe
        survey_id = survey.public_id or f"ID{survey.id}"
        
        return f"Reporte_{survey_id}_{clean_title}_{date_str}.pdf"