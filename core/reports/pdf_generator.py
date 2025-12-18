"""core/reports/pdf_generator.py"""
import json
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


def add_static_chart_images(analysis_data, include_charts: bool = True) -> None:
    """Enriquece los ítems de analysis_data con `chart_image_base64` si es posible.

    Útil para:
    - PDF (WeasyPrint no ejecuta JS)
    - Preview que quiere replicar el PDF (sin depender de Plotly/JS)
    """
    if not include_charts:
        return
    try:
        from core.utils.charts import ChartGenerator
    except Exception:
        logger.exception("No se pudo importar ChartGenerator")
        return

    for item in analysis_data or []:
        try:
            labels = item.get('chart_labels') or []
            counts = item.get('chart_data') or []
            if not labels or not counts:
                continue

            q_type = item.get('type')
            chart_b64 = None
            if q_type in ['single', 'multi', 'radio', 'select']:
                if (item.get('tipo_display') == 'doughnut') or (len(labels) <= 4):
                    chart_b64 = ChartGenerator.generate_pie_chart(labels, counts, title='', dark_mode=False)
                else:
                    chart_b64 = ChartGenerator.generate_horizontal_bar_chart(labels, counts, title='', dark_mode=False)
            elif q_type in ['scale', 'number', 'numeric']:
                chart_b64 = ChartGenerator.generate_horizontal_bar_chart(labels, counts, title='', dark_mode=False)

            if chart_b64:
                item['chart_image_base64'] = chart_b64
        except Exception:
            logger.exception("No se pudieron generar imágenes de gráficos para un ítem")

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
            
            if q_type in ['scale', 'number', 'numeric']:
                avg = insight.get('avg')
                if avg is not None:
                    metric_display = f"{avg:.1f} (Promedio)"
            
            elif q_type in ['single', 'multi', 'radio', 'select']:
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

        # Enriquecer analysis_data para PDF (WeasyPrint no ejecuta JS)
        # Generamos imágenes estáticas (base64) a partir de chart_labels/chart_data.
        for item in analysis_data or []:
            # Compat: algunos flujos aún usan total_respuestas
            if 'total_responses' not in item and 'total_respuestas' in item:
                item['total_responses'] = item.get('total_respuestas', 0)
        add_static_chart_images(analysis_data, include_charts=bool(options.get('include_charts')))

        # Contexto completo para el template
        context = {
            'survey': survey,
            'analysis': analysis_data,
            'analysis_items': analysis_data,
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
            # Compat: el template global espera variables planas y `fecha_generacion`.
            context: dict = {
                **(data or {}),
                'data': data or {},
                'generated_at': timezone.now(),
                'fecha_generacion': timezone.now(),
                'company_name': getattr(settings, 'COMPANY_NAME', 'Byteneko SaaS'),
                'is_global': True,
            }

            # Derivar distribución por categoría a partir de los campos usados en charts.
            # _get_analytics_summary entrega `categoria_labels`/`categoria_data` como JSON strings.
            labels = context.get('categoria_labels')
            values = context.get('categoria_data')
            try:
                if isinstance(labels, str):
                    labels = json.loads(labels)
                if isinstance(values, str):
                    values = json.loads(values)
                if isinstance(labels, list) and isinstance(values, list):
                    context['categoria_distribution'] = list(zip(labels, values))
            except Exception:
                context['categoria_distribution'] = None

            # Defaults numéricos amigables
            for k in ['total_surveys', 'total_active', 'total_responses']:
                if context.get(k) is None:
                    context[k] = 0
            
            # Usamos un template específico o reutilizamos uno genérico con flag is_global
            html_string = render_to_string('core/reports/_global_results_pdf.html', context)
            return HTML(string=html_string, base_url=settings.BASE_DIR).write_pdf()
            
        except Exception as e:
            logger.exception(f"Error generando reporte global PDF: {e}")
            return None