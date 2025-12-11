"""core/reports/pdf_generator.py"""
import logging
from django.template.loader import render_to_string
from django.utils import timezone
from django.conf import settings

# Intentamos importar weasyprint de forma segura
try:
    from weasyprint import HTML, CSS
except ImportError:
    HTML = None

logger = logging.getLogger(__name__)

class DataNormalizer:
    """
    Helper para normalizar datos de análisis en estructuras tabulares
    simples para previsualizaciones y reportes.
    """
    
    @staticmethod
    def prepare_consolidated_rows(analysis_data):
        """
        Transforma la lista de análisis compleja en filas planas para tablas resumen.
        Usado en report_preview_ajax.
        """
        rows = []
        for item in analysis_data:
            # Extraer métrica principal según tipo para mostrar en tabla
            metric_display = "N/A"
            insight = item.get('insight_data') or {}
            q_type = item.get('type')
            
            if q_type in ['scale', 'number']:
                avg = insight.get('avg')
                if avg is not None:
                    metric_display = f"{avg:.1f} (Promedio)"
            
            elif q_type in ['single', 'multi']:
                top = insight.get('top_option')
                if top:
                    metric_display = f"{top['option']} ({top['count']})"
            
            elif q_type == 'text':
                topics = insight.get('topics', [])
                if topics:
                    metric_display = ", ".join(topics[:2])
                else:
                    metric_display = "Texto libre"

            rows.append({
                'order': item.get('order'),
                'question': item.get('text'),
                'type': q_type,
                'total_responses': item.get('total_responses', 0),
                'metric_display': metric_display
            })
        return rows


class PDFReportGenerator:
    """
    Generador de reportes PDF basado en plantillas HTML.
    Utiliza WeasyPrint para la conversión.
    """

    @staticmethod
    def generate_report(survey, analysis_data, kpi_satisfaction_avg=0, **kwargs):
        """
        Método principal para generar el reporte de encuesta detallado.
        Adaptado para recibir los argumentos flexibles de la vista.
        
        Args:
            survey: Objeto Survey
            analysis_data: Lista de dicts con el análisis
            kpi_satisfaction_avg: Score numérico (0-10)
            **kwargs: Argumentos opcionales (start_date, end_date, include_charts, etc.)
        """
        if HTML is None:
            logger.error("WeasyPrint no está instalado. No se puede generar PDF.")
            return None

        # Preparar opciones de visualización
        options = {
            'include_charts': kwargs.get('include_charts', True),
            'include_table': kwargs.get('include_table', True),
            'include_kpis': kwargs.get('include_kpis', True),
            'start_date': kwargs.get('start_date'),
            'end_date': kwargs.get('end_date'),
            'total_responses': kwargs.get('total_responses', 0)
        }

        # Contexto completo para el template
        context = {
            'survey': survey,
            'analysis': analysis_data,
            'kpi_score': kpi_satisfaction_avg,
            'generated_at': timezone.now(),
            'options': options,
            'company_name': getattr(settings, 'COMPANY_NAME', 'Byteneko SaaS'),
            'nps_data': kwargs.get('nps_data', {}),
            'heatmap_image': kwargs.get('heatmap_image')
        }

        try:
            # Renderizar HTML usando el template corregido
            html_string = render_to_string('core/reports/report_pdf_template.html', context)
            
            # Generar PDF en memoria
            # base_url es crítico para cargar imágenes estáticas (logo, gráficos)
            pdf_file = HTML(string=html_string, base_url=settings.BASE_DIR).write_pdf()
            
            return pdf_file
            
        except Exception as e:
            logger.exception(f"Error crítico generando PDF para encuesta {survey.id}: {e}")
            return None

    @staticmethod
    def generate_global_report(data):
        """
        Genera un reporte global de métricas (Dashboard Analytics).
        """
        if HTML is None: return None
        
        try:
            context = {
                'data': data,
                'generated_at': timezone.now(),
                'company_name': getattr(settings, 'COMPANY_NAME', 'Byteneko SaaS'),
                'is_global': True
            }
            
            # Usamos un template específico o reutilizamos uno genérico con flag is_global
            html_string = render_to_string('core/reports/_global_results_pdf.html', context)
            return HTML(string=html_string, base_url=settings.BASE_DIR).write_pdf()
            
        except Exception as e:
            logger.exception(f"Error generando reporte global PDF: {e}")
            return None