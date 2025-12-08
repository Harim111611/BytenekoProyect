import logging
from datetime import datetime
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify

logger = logging.getLogger(__name__)

try:
    from weasyprint import HTML
except ImportError:
    HTML = None
    logger.warning("WeasyPrint no está instalado. La generación de PDF no funcionará.")

class PDFReportGenerator:
    @staticmethod
    def prepare_consolidated_rows(analysis_data):
        """
        Prepara filas para tablas de reporte. Optimizado para evitar recálculos innecesarios.
        """
        rows = []
        if not analysis_data:
            return rows

        for item in analysis_data:
            q_text = item.get('text', 'Sin pregunta')
            # Unificación de claves de opciones
            options = item.get('opciones') or item.get('options') or []
            total_respuestas = item.get('total_respuestas', 0)

            if options:
                for op in options:
                    count = op.get('count', 0)
                    percent = op.get('percent', 0)

                    # Recalcular solo si falta el porcentaje y hay total
                    if 'percent' not in op and total_respuestas > 0:
                        percent = (count / total_respuestas) * 100
                    
                    rows.append({
                        'question': q_text,
                        'option': op.get('label', 'Sin etiqueta'),
                        'count': count,
                        'percent': percent,
                    })
        return rows

    @staticmethod
    def generate_report(survey, analysis_data, nps_data, start_date=None, 
                       end_date=None, total_responses=0, include_table=False,
                       kpi_satisfaction_avg=0, request=None, **kwargs):
        """
        Genera un PDF basado en los datos de la encuesta usando WeasyPrint.
        """
        if not HTML:
            raise ValueError("WeasyPrint no está instalado o configurado correctamente en el servidor.")
            
        consolidated_rows = PDFReportGenerator.prepare_consolidated_rows(analysis_data)
        
        # Configuración dinámica o por defecto
        pdf_table_total = kwargs.get('pdf_table_row_limit', 40)
        
        # Saneamiento de datos NPS para evitar errores de renderizado
        nps_safe = nps_data if isinstance(nps_data, dict) else {}

        context = {
            'survey': survey,
            'start_date': start_date,
            'end_date': end_date,
            'total_respuestas': total_responses, 
            'analysis_data': analysis_data, 
            'nps_score': nps_safe.get('score'),
            'nps_promoters': nps_safe.get('promoters', 0),
            'nps_passives': nps_safe.get('passives', 0),
            'nps_detractors': nps_safe.get('detractors', 0),
            'nps_chart_image': nps_safe.get('chart_image'),
            'heatmap_image': kwargs.get('heatmap_image'),
            'kpi_prom_satisfaccion': kpi_satisfaction_avg, 
            'include_table': include_table,
            'include_kpis': True,
            'include_charts': True,
            'fecha_generacion': timezone.now(),
            'is_pdf': True,
            'consolidated_table_rows': consolidated_rows,
            'consolidated_table_rows_limited': consolidated_rows[:pdf_table_total],
            'pdf_table_total_row_limit': pdf_table_total,
        }

        try:
            html_string = render_to_string('core/reports/report_pdf_template.html', context)
            base_url = request.build_absolute_uri('/') if request else None
            return HTML(string=html_string, base_url=base_url).write_pdf()
        except Exception as e:
            logger.error(f"Error generando PDF para encuesta {survey.id}: {str(e)}")
            raise e

    @staticmethod
    def get_filename(survey):
        """Genera un nombre de archivo seguro usando slugify."""
        clean_title = slugify(survey.title)[:50]
        timestamp = timezone.now().strftime('%Y%m%d_%H%M')
        return f"Reporte_{clean_title}_{timestamp}.pdf"