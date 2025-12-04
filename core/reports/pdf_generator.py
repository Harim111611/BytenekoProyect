import re
from datetime import datetime
from django.template.loader import render_to_string
from django.utils import timezone

try:
    from weasyprint import HTML
except ImportError:
    HTML = None

class PDFReportGenerator:
    @staticmethod
    def generate_report(survey, analysis_data, nps_data, start_date=None, 
                       end_date=None, total_responses=0, include_table=False,
                       kpi_satisfaction_avg=0, request=None, **kwargs):
        if not HTML:
            raise ValueError("WeasyPrint es necesario para generar PDFs.")
            
        context = {
            'survey': survey,
            'start_date': start_date,
            'end_date': end_date,
            'total_respuestas': total_responses, 
            'analysis_data': analysis_data, # Ahora incluye chart_image y mejores insights
            'nps_score': nps_data.get('score'),
            'nps_promoters': nps_data.get('promoters', 0),
            'nps_passives': nps_data.get('passives', 0),
            'nps_detractors': nps_data.get('detractors', 0),
            'nps_chart_image': nps_data.get('chart_image'),
            'heatmap_image': kwargs.get('heatmap_image'),
            'kpi_prom_satisfaccion': kpi_satisfaction_avg, 
            'include_table': include_table,
            'include_kpis': True,
            'include_charts': True,  # Essential for _report_preview_content.html to render questions
            'fecha_generacion': timezone.now(),
        }
        
        # El template report_pdf_template.html comparte estructura con _report_preview_content.html
        # por lo que las gráficas funcionarán automáticamente.
        html_string = render_to_string('core/reports/report_pdf_template.html', context)
        base_url = request.build_absolute_uri('/') if request else None
        
        return HTML(string=html_string, base_url=base_url).write_pdf()

    @staticmethod
    def get_filename(survey):
        clean_title = re.sub(r'[^\w\s-]', '', survey.title[:30]).replace(' ', '_')
        return f"Reporte_{clean_title}_{datetime.now().strftime('%Y%m%d')}.pdf"