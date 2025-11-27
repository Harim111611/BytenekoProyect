"""
PDF Report Generator using WeasyPrint.
"""
import re
from datetime import datetime
from django.template.loader import render_to_string

try:
    from weasyprint import HTML
except ImportError:
    HTML = None


class PDFReportGenerator:
    """PDF Report Generator."""
    
    @staticmethod
    def generate_report(survey, analysis_data, nps_data, start_date=None, 
                       end_date=None, total_responses=0, include_table=False,
                       kpi_satisfaction_avg=0, request=None, **kwargs):
        """
        Generates a PDF report for a survey.
        """
        if not HTML:
            raise ValueError("WeasyPrint is not installed")
        
        # Map English params to Spanish keys for template compatibility
        context = {
            'survey': survey,
            'start_date': start_date,
            'end_date': end_date,
            'total_respuestas': total_responses, 
            'analysis_data': analysis_data,
            'nps_score': nps_data['score'],
            'kpi_prom_satisfaccion': kpi_satisfaction_avg, 
            'include_table': include_table,
        }
        
        html_string = render_to_string('core/report_pdf_template.html', context)
        
        base_url = request.build_absolute_uri() if request else None
        
        try:
            pdf_file = HTML(string=html_string, base_url=base_url).write_pdf()
            return pdf_file
        except Exception as e:
            raise ValueError(f"Error generating PDF: {e}")
    
    @staticmethod
    def get_filename(survey):
        """Generates a clean filename for the PDF."""
        clean_title = re.sub(r'[^\w\s-]', '', survey.title[:20])
        date_str = datetime.now().strftime('%Y%m%d')
        return f"Reporte_{clean_title}_{date_str}.pdf"