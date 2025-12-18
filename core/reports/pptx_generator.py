"""core/reports/pptx_generator.py"""
import base64
import io
import logging
from dataclasses import dataclass
from typing import Tuple, Optional
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PPTXStyleConfig:
    """Configuración mínima de estilos para PPTX (compat y extensibilidad)."""

    title_max_len: int = 80


class PPTXSlideBuilder:
    """Wrapper liviano para compatibilidad con tests/uso previo."""

    def __init__(self, prs: Presentation):
        self.prs = prs


class PPTXReportGenerator:
    """API de compatibilidad.

    El proyecto exporta vía `generate_full_pptx_report`, pero algunos tests
    esperan estas utilidades.
    """

    @staticmethod
    def _clean_title(title: str) -> str:
        return (title or "").strip()

    @staticmethod
    def _split_question_title(title: str) -> Tuple[str, str]:
        title = (title or "").strip()
        if not title:
            return "", ""
        if '(' in title and title.endswith(')'):
            base, extra = title.rsplit('(', 1)
            base = base.strip()
            extra = '(' + extra
            return base, extra
        return title, ""

    @staticmethod
    def _is_text_like_question(item: dict) -> bool:
        q_type = (item or {}).get('type')
        return q_type == 'text'

    @classmethod
    def generate(
        cls,
        survey,
        analysis_data,
        kpi_satisfaction_avg: float = 0,
        **kwargs,
    ):
        return generate_full_pptx_report(
            survey=survey,
            analysis_data=analysis_data,
            kpi_satisfaction_avg=kpi_satisfaction_avg,
            **kwargs,
        )


def _add_chart_image(slide, left, top, width, chart_b64: str) -> None:
    if not chart_b64:
        return
    try:
        img_bytes = base64.b64decode(chart_b64)
        slide.shapes.add_picture(io.BytesIO(img_bytes), left, top, width=width)
    except Exception:
        # Si falla la imagen, preferimos un PPTX sin gráfico antes que romper export.
        logger.exception("No se pudo incrustar imagen de gráfico en PPTX")


def _metric_display_for_item(item: dict) -> str:
    q_type = item.get('type')
    insight = item.get('insight_data') or {}
    if q_type in ['scale', 'number', 'numeric']:
        avg = insight.get('avg') if insight.get('avg') is not None else insight.get('average')
        if avg is None:
            return "Promedio: N/A"
        return f"Promedio: {float(avg):.1f}"
    if q_type in ['single', 'multi', 'radio', 'select']:
        top = insight.get('top_option')
        if top and top.get('option') is not None:
            return f"Top: {top.get('option')} ({top.get('count', 0)})"
        return "Top: N/A"
    if q_type == 'text':
        topics = insight.get('topics') or []
        if topics:
            return "Temas: " + ", ".join([str(t) for t in topics[:3]])
        return "Temas: N/A"
    return ""

def generate_full_pptx_report(survey, analysis_data, kpi_satisfaction_avg=0, **kwargs):
    """
    Genera un reporte completo en PowerPoint (.pptx).
    Función adaptada para ser llamada directamente desde la vista.
    
    Args:
        survey: Instancia del modelo Survey.
        analysis_data: Lista de dicts con el análisis.
        kpi_satisfaction_avg: Score numérico (0-10).
        **kwargs: Argumentos opcionales (start_date, end_date, total_responses, etc.)
    """
    # 1. Crear Presentación
    prs = Presentation()
    
    # 2. Configurar metadatos del reporte
    start_date = kwargs.get('start_date')
    end_date = kwargs.get('end_date')
    date_str = timezone.now().strftime('%d/%m/%Y')
    
    if start_date and end_date:
        period_info = f"Periodo: {start_date} al {end_date}"
    else:
        period_info = f"Generado el: {date_str}"

    include_charts = kwargs.get('include_charts', True)
    include_table = kwargs.get('include_table', True)

    # --- DIAPOSITIVA 1: PORTADA ---
    title_slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(title_slide_layout)
    
    title = slide.shapes.title
    subtitle = slide.placeholders[1]
    
    title.text = survey.title
    subtitle.text = (
        f"Reporte de Resultados\n"
        f"{period_info}\n"
        f"Índice Global de Satisfacción: {kpi_satisfaction_avg:.1f}/10"
    )

    # --- DIAPOSITIVA 2: RESUMEN EJECUTIVO ---
    bullet_slide_layout = prs.slide_layouts[1]
    slide = prs.slides.add_slide(bullet_slide_layout)
    
    title = slide.shapes.title
    title.text = "Resumen Ejecutivo"
    
    body_shape = slide.shapes.placeholders[1]
    tf = body_shape.text_frame
    
    # Métricas generales
    p = tf.add_paragraph()
    total_responses = kwargs.get('total_responses', 0)
    p.text = f"Total de Respuestas Analizadas: {total_responses}"
    
    p = tf.add_paragraph()
    p.text = f"Calificación General: {kpi_satisfaction_avg:.1f} / 10"
    p.level = 0

    # Hallazgos Clave (Top Insights)
    top_insights = [
        item for item in analysis_data 
        if item.get('insight_data', {}).get('mood') in ['CRITICO', 'EXCELENTE']
    ]
    
    if top_insights:
        p = tf.add_paragraph()
        p.text = "Puntos Destacados:"
        p.level = 0
        
        for item in top_insights[:3]:
            insight = item.get('insight_data', {})
            mood = insight.get('mood', 'NEUTRO')
            score = insight.get('avg', 0)

            sub_p = tf.add_paragraph()
            sub_p.text = f"{mood}: {item.get('text', '')} (Score: {float(score):.1f})"
            sub_p.level = 1

    # --- DIAPOSITIVA 3 (OPCIONAL): TABLA RESUMEN ---
    if include_table:
        slide = prs.slides.add_slide(bullet_slide_layout)
        slide.shapes.title.text = "Tabla Resumen"
        body_shape = slide.shapes.placeholders[1]
        tf = body_shape.text_frame
        tf.clear()
        p0 = tf.paragraphs[0]
        p0.text = "Métricas clave por pregunta (top 15)"
        p0.font.bold = True
        p0.font.size = Pt(18)

        for item in (analysis_data or [])[:15]:
            p = tf.add_paragraph()
            p.text = f"{item.get('order', '')}. {_metric_display_for_item(item)}"
            p.level = 1

    # --- DIAPOSITIVAS DETALLE (Por Pregunta) ---
    chart_layout = prs.slide_layouts[5] # Layout "Title Only" para flexibilidad
    
    for item in analysis_data:
        slide = prs.slides.add_slide(chart_layout)
        title = slide.shapes.title
        
        # Limpiar título largo
        clean_title = f"{item['order']}. {item['text']}"
        if len(clean_title) > 80:
            clean_title = clean_title[:77] + "..."
        title.text = clean_title
        
        # Contenedor de Métricas (Izquierda)
        left_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(4.4), Inches(3.8))
        tf = left_box.text_frame
        tf.word_wrap = True
        
        insight = item.get('insight_data', {})
        q_type = item.get('type')
        
        # Lógica de renderizado según tipo de pregunta
        if q_type in ['scale', 'number', 'numeric']:
            p = tf.add_paragraph()
            avg_val = insight.get('avg') if insight.get('avg') is not None else insight.get('average', 0)
            p.text = f"Promedio: {float(avg_val):.1f}"
            p.font.size = Pt(36)
            p.font.bold = True
            p.font.color.rgb = RGBColor(0, 80, 158) # Azul Byteneko
            
            if insight.get('trend_delta'):
                p2 = tf.add_paragraph()
                delta = insight.get('trend_delta')
                symbol = "▲" if delta > 0 else "▼"
                color = RGBColor(0, 128, 0) if delta > 0 else RGBColor(204, 0, 0)
                
                p2.text = f"{symbol} {abs(delta):.1f}% vs periodo anterior"
                p2.font.size = Pt(14)
                p2.font.color.rgb = color

        elif q_type in ['single', 'multi', 'radio', 'select']:
            top = insight.get('top_option')
            if top:
                p = tf.add_paragraph()
                p.text = "Opción Principal:"
                p.font.bold = True
                p.font.size = Pt(18)
                
                p2 = tf.add_paragraph()
                p2.text = f"{top['option']}"
                p2.font.size = Pt(24)
                p2.font.color.rgb = RGBColor(0, 102, 0) # Verde
                
                total = insight.get('total', 1)
                pct = (top['count'] / total * 100) if total else 0
                
                p3 = tf.add_paragraph()
                p3.text = f"{top['count']} votos ({pct:.1f}%)"
                p3.font.size = Pt(14)

        elif q_type == 'text':
            p = tf.add_paragraph()
            p.text = "Temas Recurrentes:"
            p.font.bold = True
            
            topics = insight.get('topics', [])
            if topics:
                for t in topics:
                    bp = tf.add_paragraph()
                    bp.text = f"• {t}"
                    bp.level = 1
            else:
                tf.add_paragraph().text = "No se detectaron temas claros."

        # Contenedor de gráfico (Derecha) - imagen estática
        if include_charts:
            try:
                from core.utils.charts import ChartGenerator

                labels = item.get('chart_labels') or []
                counts = item.get('chart_data') or []
                chart_b64 = None
                if labels and counts:
                    if q_type in ['single', 'multi', 'radio', 'select']:
                        if (item.get('tipo_display') == 'doughnut') or (len(labels) <= 4):
                            chart_b64 = ChartGenerator.generate_pie_chart(labels, counts, title='', dark_mode=False)
                        else:
                            chart_b64 = ChartGenerator.generate_horizontal_bar_chart(labels, counts, title='', dark_mode=False)
                    elif q_type in ['scale', 'number', 'numeric']:
                        chart_b64 = ChartGenerator.generate_horizontal_bar_chart(labels, counts, title='', dark_mode=False)

                if chart_b64:
                    _add_chart_image(slide, Inches(5.1), Inches(1.5), Inches(4.4), chart_b64)
            except Exception:
                logger.exception("No se pudo generar/incrustar gráfico para una diapositiva")

        # Contenedor de Narrativa Automática (Abajo)
        if insight.get('narrative'):
            nar_box = slide.shapes.add_textbox(Inches(0.5), Inches(5.4), Inches(9.0), Inches(1.6))
            nf = nar_box.text_frame
            nf.word_wrap = True
            
            p_head = nf.add_paragraph()
            p_head.text = "Análisis IA:"
            p_head.font.bold = True
            p_head.font.size = Pt(11)
            p_head.font.color.rgb = RGBColor(100, 100, 100)
            
            p_body = nf.add_paragraph()
            p_body.text = f"\"{insight['narrative']}\""
            p_body.font.italic = True
            p_body.font.size = Pt(12)

    # 4. Guardar en memoria y retornar
    output = io.BytesIO()
    prs.save(output)
    output.seek(0)
    return output