"""
PowerPoint Report Generator using python-pptx.
Diseño v4: Optimizado y Modular.
"""
import io
import re
import base64
import logging
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

logger = logging.getLogger(__name__)

class PPTXStyleConfig:
    COLOR_PRIMARY = RGBColor(13, 110, 253)    # Bootstrap Primary
    COLOR_DARK = RGBColor(31, 41, 55)         # Gray 800
    COLOR_MUTED = RGBColor(107, 114, 129)     # Gray 500
    COLOR_BG_LIGHT = RGBColor(249, 250, 251)  # Gray 50
    COLOR_WHITE = RGBColor(255, 255, 255)
    SLIDE_WIDTH = Inches(13.333)
    SLIDE_HEIGHT = Inches(7.5)

class PPTXSlideBuilder:
    def __init__(self, presentation):
        self.prs = presentation
        self.style = PPTXStyleConfig

    def add_slide(self):
        # Layout 6 es usualmente 'Blank' en temas standard
        return self.prs.slides.add_slide(self.prs.slide_layouts[6])

    def apply_header(self, slide, title_text):
        """Header estilo corporativo con barra de acento."""
        # Top Bar
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, self.style.SLIDE_WIDTH, Inches(0.15))
        bar.fill.solid()
        bar.fill.fore_color.rgb = self.style.COLOR_PRIMARY
        bar.line.fill.background()

        # Title
        tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(10), Inches(0.8))
        p = tb.text_frame.paragraphs[0]
        p.text = title_text
        p.font.size = Pt(24)
        p.font.bold = True
        p.font.color.rgb = self.style.COLOR_DARK
        
        # Logo placeholder
        tb_logo = slide.shapes.add_textbox(Inches(10.8), Inches(0.35), Inches(2), Inches(0.5))
        p_l = tb_logo.text_frame.paragraphs[0]
        p_l.text = "BYTENEKO"
        p_l.alignment = PP_ALIGN.RIGHT
        p_l.font.bold = True
        p_l.font.color.rgb = self.style.COLOR_MUTED

    def draw_kpi_card(self, slide, x, y, width, title, value, color=None):
        if not color: color = self.style.COLOR_PRIMARY
        
        # Card container
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, width, Inches(1.8))
        shape.fill.solid()
        shape.fill.fore_color.rgb = self.style.COLOR_WHITE
        shape.line.color.rgb = RGBColor(229, 231, 235)
        shape.shadow.inherit = False
        
        # Value
        tb_v = slide.shapes.add_textbox(x, y + Inches(0.4), width, Inches(0.8))
        p_v = tb_v.text_frame.paragraphs[0]
        p_v.text = str(value)
        p_v.font.size = Pt(40)
        p_v.font.bold = True
        p_v.alignment = PP_ALIGN.CENTER
        p_v.font.color.rgb = color
        
        # Label
        tb_l = slide.shapes.add_textbox(x, y + Inches(1.2), width, Inches(0.4))
        p_l = tb_l.text_frame.paragraphs[0]
        p_l.text = str(title).upper()
        p_l.font.size = Pt(10)
        p_l.alignment = PP_ALIGN.CENTER
        p_l.font.color.rgb = self.style.COLOR_MUTED

class PPTXReportGenerator:
    @staticmethod
    def _add_image_safe(slide, b64_string, x, y, width=None, height=None):
        """Intenta decodificar y agregar una imagen base64 de forma segura."""
        if not b64_string:
            return None
        try:
            # Limpiar cabeceras tipo data:image/png;base64, si existen
            if ',' in b64_string:
                b64_string = b64_string.split(',')[1]
                
            img_data = base64.b64decode(b64_string)
            img_stream = io.BytesIO(img_data)
            pic = slide.shapes.add_picture(img_stream, x, y, width=width, height=height)
            return pic
        except Exception as e:
            logger.warning(f"Error agregando imagen al PPTX: {e}")
            return None

    @staticmethod
    def generate_report(survey, analysis_data, nps_data, heatmap_image, date_range_label, responses_queryset, **kwargs):
        prs = Presentation()
        prs.slide_width = PPTXStyleConfig.SLIDE_WIDTH
        prs.slide_height = PPTXStyleConfig.SLIDE_HEIGHT
        
        builder = PPTXSlideBuilder(prs)
        response_count = responses_queryset.count()
        
        # 1. PORTADA
        PPTXReportGenerator._create_cover_slide(builder, survey, date_range_label, response_count)

        # 2. KPIS + NPS
        PPTXReportGenerator._create_kpi_slide(builder, nps_data, response_count, kwargs.get('kpi_satisfaction_avg'))

        # 3. HEATMAP
        if heatmap_image:
            PPTXReportGenerator._create_heatmap_slide(builder, heatmap_image)

        # 4. PREGUNTAS INDIVIDUALES
        for item in analysis_data:
            PPTXReportGenerator._create_question_slide(builder, item, kwargs.get('include_table', False))

        f = io.BytesIO()
        prs.save(f)
        f.seek(0)
        return f

    @staticmethod
    def _create_cover_slide(builder, survey, date_range, count):
        slide = builder.add_slide()
        # Fondo Split
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(6.5), PPTXStyleConfig.SLIDE_HEIGHT)
        bg.fill.solid()
        bg.fill.fore_color.rgb = PPTXStyleConfig.COLOR_BG_LIGHT
        bg.line.fill.background()
        
        # Título
        tb = slide.shapes.add_textbox(Inches(0.5), Inches(2.5), Inches(5.5), Inches(3))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = survey.title
        p.font.size = Pt(36)
        p.font.bold = True
        p.font.color.rgb = PPTXStyleConfig.COLOR_PRIMARY
        
        p2 = tf.add_paragraph()
        p2.text = "Reporte Ejecutivo"
        p2.font.size = Pt(18)
        p2.font.color.rgb = PPTXStyleConfig.COLOR_MUTED
        p2.space_before = Pt(20)
        
        # Ficha Técnica
        tb_ctx = slide.shapes.add_textbox(Inches(7.0), Inches(2.5), Inches(5.8), Inches(4))
        pc = tb_ctx.text_frame.paragraphs[0]
        pc.text = "FICHA TÉCNICA"
        pc.font.bold = True
        pc.font.color.rgb = PPTXStyleConfig.COLOR_DARK
        
        desc = (survey.description or 'Sin descripción').strip()
        if len(desc) > 150: desc = desc[:150] + "..."

        details = [
            f"Periodo: {date_range}",
            f"Total Respuestas: {count}",
            f"Descripción: {desc}"
        ]
        for d in details:
            p = tb_ctx.text_frame.add_paragraph()
            p.text = f"• {d}"
            p.font.size = Pt(14)
            p.space_after = Pt(15)

    @staticmethod
    def _create_kpi_slide(builder, nps_data, count, satisfaction_avg):
        slide = builder.add_slide()
        builder.apply_header(slide, "Panorama General")
        
        # Resumen Texto
        tb = slide.shapes.add_textbox(Inches(0.5), Inches(1.2), Inches(12.3), Inches(0.8))
        tb.text_frame.paragraphs[0].text = f"Resumen de {count} respuestas. Indicadores clave de desempeño:"
        tb.text_frame.paragraphs[0].font.color.rgb = PPTXStyleConfig.COLOR_MUTED
        
        # Tarjetas
        sat_val = f"{(satisfaction_avg or 0):.1f}"
        nps_val = nps_data.get('score') if isinstance(nps_data, dict) else '--'
        
        builder.draw_kpi_card(slide, Inches(0.5), Inches(2.2), Inches(3.8), "Respuestas", count)
        builder.draw_kpi_card(slide, Inches(4.5), Inches(2.2), Inches(3.8), "Satisfacción", sat_val, PPTXStyleConfig.COLOR_DARK)
        builder.draw_kpi_card(slide, Inches(8.5), Inches(2.2), Inches(3.8), "NPS", nps_val, RGBColor(16, 185, 129))

        # NPS Chart
        if isinstance(nps_data, dict) and nps_data.get('chart_image'):
            PPTXReportGenerator._add_image_safe(slide, nps_data['chart_image'], Inches(4.5), Inches(4.5), height=Inches(2.8))

    @staticmethod
    def _create_heatmap_slide(builder, heatmap_b64):
        slide = builder.add_slide()
        builder.apply_header(slide, "Mapa de Correlaciones")
        
        tb = slide.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(12.3), Inches(1))
        p = tb.text_frame.paragraphs[0]
        p.text = "Relación entre variables numéricas (+1 correlación positiva, -1 negativa, 0 nula)."
        p.font.color.rgb = PPTXStyleConfig.COLOR_MUTED
        
        PPTXReportGenerator._add_image_safe(slide, heatmap_b64, Inches(1.5), Inches(2.8), height=Inches(4))

    @staticmethod
    def _create_question_slide(builder, item, include_table):
        slide = builder.add_slide()
        builder.apply_header(slide, f"{item.get('order',0)}. {item.get('text','')}")
        
        left_x, right_x = Inches(0.5), Inches(6.8)
        col_w = Inches(6.0)
        curr_y_left, curr_y_right = Inches(1.5), Inches(1.5)

        # IZQUIERDA: Insights
        if item.get('insight'):
            clean_ins = re.sub(r'<[^>]+>', '', item['insight']).replace('&nbsp;', ' ')
            
            # Caja Insight
            bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left_x, curr_y_left, col_w, Inches(2.5))
            bg.fill.solid()
            bg.fill.fore_color.rgb = RGBColor(239, 246, 255) # Blue 50
            bg.line.color.rgb = RGBColor(191, 219, 254)
            
            tb = slide.shapes.add_textbox(left_x + Inches(0.1), curr_y_left + Inches(0.1), col_w - Inches(0.2), Inches(2.3))
            p = tb.text_frame.paragraphs[0]
            p.text = f"ANÁLISIS: {clean_ins}"
            p.font.size = Pt(13)
            p.font.color.rgb = RGBColor(30, 58, 138)
            p.alignment = PP_ALIGN.JUSTIFY
            tf = tb.text_frame
            tf.word_wrap = True
            
            curr_y_left += Inches(2.7)

        # IZQUIERDA: Recomendaciones
        recs = item.get('recommendations', [])
        if recs:
            # Caja Recomendaciones
            bg_rec = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left_x, curr_y_left, col_w, Inches(2.0))
            bg_rec.fill.solid()
            bg_rec.fill.fore_color.rgb = RGBColor(240, 253, 244) # Green 50
            bg_rec.line.color.rgb = RGBColor(34, 197, 94)
            
            tb_rec = slide.shapes.add_textbox(left_x + Inches(0.1), curr_y_left + Inches(0.1), col_w - Inches(0.2), Inches(1.8))
            p = tb_rec.text_frame.paragraphs[0]
            p.text = "RECOMENDACIONES:"
            p.font.bold = True
            p.font.color.rgb = RGBColor(21, 128, 61)
            
            for r in recs[:4]:
                p = tb_rec.text_frame.add_paragraph()
                p.text = f"• {r}"
                p.font.size = Pt(11)
                p.font.color.rgb = RGBColor(22, 101, 52)
            
            curr_y_left += Inches(2.2)

        # DERECHA: Gráfico
        if item.get('chart_image'):
            pic = PPTXReportGenerator._add_image_safe(slide, item['chart_image'], right_x, curr_y_right, width=col_w)
            if pic:
                curr_y_right += pic.height + Inches(0.2)

        # DERECHA: Tabla (Fallback simple si no hay espacio para tabla compleja)
        opts = item.get('options') or []
        if include_table and opts and curr_y_right < Inches(6.5):
            # Renderizado simplificado de tabla
            max_rows = 10
            rows_to_show = opts[:max_rows]
            
            # Crear tabla
            try:
                table_shape = slide.shapes.add_table(len(rows_to_show)+1, 3, right_x, curr_y_right, col_w, Inches(0.3 * len(rows_to_show)))
                tbl = table_shape.table
                
                # Headers
                headers = ['Opción', 'Frecuencia', '%']
                for idx, txt in enumerate(headers):
                    tbl.cell(0, idx).text = txt
                    tbl.cell(0, idx).text_frame.paragraphs[0].font.bold = True
                
                # Rows
                for i, op in enumerate(rows_to_show):
                    tbl.cell(i+1, 0).text = str(op.get('label', ''))[:40]
                    tbl.cell(i+1, 1).text = str(op.get('count', 0))
                    tbl.cell(i+1, 2).text = f"{op.get('percent', 0):.1f}%"
                    
                    # Size adjustment
                    for c in range(3):
                        tbl.cell(i+1, c).text_frame.paragraphs[0].font.size = Pt(10)
            except Exception:
                # Fallback text
                pass