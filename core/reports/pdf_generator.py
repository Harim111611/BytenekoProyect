import logging
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, asdict
from datetime import datetime

from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings

logger = logging.getLogger(__name__)

# Intento seguro de importación
try:
    from weasyprint import HTML, CSS
except ImportError:
    HTML = None
    CSS = None

@dataclass
class PDFReportContext:
    """Estructura de datos tipada para el contexto del template PDF."""
    survey: Any
    analysis_data: List[Dict[str, Any]]
    start_date: Optional[str]
    end_date: Optional[str]
    total_respuestas: int
    fecha_generacion: datetime
    
    # NPS Fields
    nps_score: Union[int, float, str]
    nps_promoters: int
    nps_passives: int
    nps_detractors: int
    nps_chart_image: Optional[str]
    
    # Visuals & KPI
    heatmap_image: Optional[str]
    kpi_prom_satisfaccion: float
    include_table: bool
    include_kpis: bool = True
    include_charts: bool = True
    
    # Table Data
    consolidated_table_rows: List[Dict[str, Any]] = None
    consolidated_table_rows_limited: List[Dict[str, Any]] = None
    pdf_table_total_row_limit: int = 200  # MODIFICADO: Default aumentado a 200
    is_pdf: bool = True

class DataNormalizer:
    """Helper para limpiar y estructurar datos crudos."""
    
    @staticmethod
    def prepare_consolidated_rows(analysis_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows = []
        if not analysis_data:
            return rows

        for item in analysis_data:
            q_text = item.get('text', 'Pregunta sin texto')
            options = item.get('opciones') or item.get('options') or []
            total = item.get('total_respuestas', 0)

            if not options:
                continue

            for op in options:
                count = op.get('count', 0)
                percent = op.get('percent', 0)
                if percent == 0 and total > 0:
                    percent = (count / total) * 100
                
                rows.append({
                    'question': q_text,
                    'option': op.get('label', 'Sin etiqueta'),
                    'count': count,
                    'percent': percent,
                })
        return rows

    @staticmethod
    def safe_nps_extract(nps_data: Optional[Dict]) -> Dict[str, Any]:
        safe_data = nps_data if isinstance(nps_data, dict) else {}
        return {
            'score': safe_data.get('score', 0),
            'promoters': safe_data.get('promoters', 0),
            'passives': safe_data.get('passives', 0),
            'detractors': safe_data.get('detractors', 0),
            'chart_image': safe_data.get('chart_image'),
        }

class PDFReportGenerator:
    """
    Servicio enterprise para generación de reportes PDF.
    """

    TEMPLATE_PATH = 'core/reports/report_pdf_template.html'
    
    # CSS REFORZADO: Lógica de contención estricta para saltos de página
    FORCE_PAGE_BREAKS_CSS = """
    @page {
        size: A4;
        margin: 1.0cm; /* Márgenes ajustados para aprovechar espacio */
    }
    
    /* REGLA DE ORO: Todo el bloque de la pregunta es indivisible.
       Si no cabe, se va completo a la siguiente página.
    */
    .question-block, .question-container, .analysis-card {
        page-break-inside: avoid !important;
        margin-bottom: 20px;
        display: block;
    }

    /* Asegurar que las imágenes/gráficos no se corten */
    img, .chart-container {
        page-break-inside: avoid !important;
        max-width: 100%;
    }

    /* Títulos siempre pegados a su contenido */
    h2, h3, .card-header {
        page-break-after: avoid !important;
    }
    
    /* Tablas pequeñas se mantienen unidas, filas no se rompen */
    tr, td, th {
        page-break-inside: avoid !important;
    }
    """

    @classmethod
    def check_dependency(cls):
        if HTML is None:
            msg = "WeasyPrint no está instalado. Instale 'weasyprint'."
            logger.critical(msg)
            raise ImproperlyConfigured(msg)

    @staticmethod
    def prepare_consolidated_rows(analysis_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return DataNormalizer.prepare_consolidated_rows(analysis_data)

    @staticmethod
    def generate_report(
        survey: Any,
        analysis_data: List[Dict],
        nps_data: Optional[Dict],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        total_responses: int = 0,
        include_table: bool = False,
        kpi_satisfaction_avg: float = 0,
        request: Any = None,
        **kwargs
    ) -> bytes:
        PDFReportGenerator.check_dependency()

        try:
            # 0. Ordenamiento Crítico
            if analysis_data:
                analysis_data.sort(key=lambda x: x.get('order', float('inf')))

            # 1. Preparación de Datos
            consolidated = DataNormalizer.prepare_consolidated_rows(analysis_data)
            nps_clean = DataNormalizer.safe_nps_extract(nps_data)
            
            # MODIFICADO: Leemos el límite de kwargs, default 200
            limit = kwargs.get('pdf_table_row_limit', 200)

            # 2. Contexto
            ctx_obj = PDFReportContext(
                survey=survey,
                analysis_data=analysis_data,
                start_date=start_date,
                end_date=end_date,
                total_respuestas=total_responses,
                fecha_generacion=timezone.now(),
                nps_score=nps_clean['score'],
                nps_promoters=nps_clean['promoters'],
                nps_passives=nps_clean['passives'],
                nps_detractors=nps_clean['detractors'],
                nps_chart_image=nps_clean['chart_image'],
                heatmap_image=kwargs.get('heatmap_image'),
                kpi_prom_satisfaccion=kpi_satisfaction_avg or 0.0,
                include_table=include_table,
                consolidated_table_rows=consolidated,
                consolidated_table_rows_limited=consolidated[:limit], # Aplica el límite de 200
                pdf_table_total_row_limit=limit
            )

            # 3. Renderizado HTML
            html_string = render_to_string(
                PDFReportGenerator.TEMPLATE_PATH, 
                asdict(ctx_obj)
            )
            
            # 4. Configuración URL para assets estáticos
            base_url = None
            if request:
                base_url = request.build_absolute_uri('/')
            elif hasattr(settings, 'STATIC_ROOT') and settings.STATIC_ROOT:
                 base_url = f"file://{settings.STATIC_ROOT}"

            logger.info(f"Generando PDF para Encuesta ID: {getattr(survey, 'id', 'unknown')}")
            
            # 5. Generación PDF con inyección de CSS reforzado
            return HTML(string=html_string, base_url=base_url).write_pdf(
                stylesheets=[CSS(string=PDFReportGenerator.FORCE_PAGE_BREAKS_CSS)]
            )

        except Exception as e:
            logger.error(
                f"Fallo crítico en generación PDF (Survey {getattr(survey, 'id', '?')}): {e}", 
                exc_info=True
            )
            raise e

    @staticmethod
    def get_filename(survey: Any) -> str:
        title = getattr(survey, 'title', 'reporte')
        clean_title = slugify(title)[:50]
        timestamp = timezone.now().strftime('%Y%m%d_%H%M')
        return f"Reporte_{clean_title}_{timestamp}.pdf"