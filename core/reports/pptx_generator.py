"""
PowerPoint Report Generator using python-pptx.
Diseño v4: Texto Justificado, Más Contexto, Espacios optimizados.
"""
import io
import re
import base64
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

class PPTXStyleConfig:
    COLOR_PRIMARY = RGBColor(13, 110, 253)
    COLOR_DARK = RGBColor(31, 41, 55)
    COLOR_MUTED = RGBColor(107, 114, 129)
    COLOR_BG_LIGHT = RGBColor(249, 250, 251)
    SLIDE_WIDTH = Inches(13.333)
    SLIDE_HEIGHT = Inches(7.5)

class PPTXSlideBuilder:
    def __init__(self, presentation):
        self.prs = presentation
        self.style = PPTXStyleConfig

    def add_slide(self):
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
        
        # Logo placeholder text
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
        shape.fill.fore_color.rgb = RGBColor(255, 255, 255)
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
        p_l.text = title.upper()
        p_l.font.size = Pt(10)
        p_l.alignment = PP_ALIGN.CENTER
        p_l.font.color.rgb = self.style.COLOR_MUTED

class PPTXReportGenerator:
    @staticmethod
    def generate_report(survey, analysis_data, nps_data, heatmap_image, date_range_label, responses_queryset, **kwargs):
        prs = Presentation()
        prs.slide_width = PPTXStyleConfig.SLIDE_WIDTH
        prs.slide_height = PPTXStyleConfig.SLIDE_HEIGHT
        
        builder = PPTXSlideBuilder(prs)
        
        # SLIDE 1: PORTADA (Con contexto)
        slide = builder.add_slide()
        
        # Background split - Ampliado para dar más aire al título
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(6.5), PPTXStyleConfig.SLIDE_HEIGHT)
        bg.fill.solid()
        bg.fill.fore_color.rgb = PPTXStyleConfig.COLOR_BG_LIGHT
        bg.line.fill.background()
        
        # Title Content - Ajustado con word_wrap y más ancho
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
        
        # Context Box (Right side) - Desplazado a la derecha
        tb_ctx = slide.shapes.add_textbox(Inches(7.0), Inches(2.5), Inches(5.8), Inches(4))
        tf_ctx = tb_ctx.text_frame
        tf_ctx.word_wrap = True
        
        pc = tf_ctx.paragraphs[0]
        pc.text = "FICHA TÉCNICA"
        pc.font.bold = True
        pc.font.color.rgb = PPTXStyleConfig.COLOR_DARK
        pc.space_after = Pt(20)
        
        details = [
            f"Periodo: {date_range_label}",
            f"Total de Respuestas: {responses_queryset.count()}",
            f"Descripción: {(survey.description or 'Sin descripción adicional').strip()[:150]}"
        ]
        
        for d in details:
            p = tf_ctx.add_paragraph()
            p.text = f"• {d}"
            p.font.size = Pt(14)
            p.alignment = PP_ALIGN.JUSTIFY
            p.space_after = Pt(15)

        # SLIDE 2: KPIs + NPS DONUT (consistencia con Preview/PDF)
        slide = builder.add_slide()
        builder.apply_header(slide, "Panorama General")
        
        # Executive summary
        tb_exec = slide.shapes.add_textbox(Inches(0.5), Inches(1.2), Inches(12.3), Inches(0.8))
        tf_exec = tb_exec.text_frame
        tf_exec.word_wrap = True
        p_exec = tf_exec.paragraphs[0]
        p_exec.text = f"Esta encuesta recopiló {responses_queryset.count()} respuestas durante el periodo analizado. Los indicadores clave reflejan el estado general de satisfacción y compromiso de la audiencia, permitiendo identificar fortalezas y áreas de oportunidad estratégicas."
        p_exec.font.size = Pt(12)
        p_exec.alignment = PP_ALIGN.JUSTIFY
        p_exec.font.color.rgb = PPTXStyleConfig.COLOR_MUTED
        
        # KPI Cards
        builder.draw_kpi_card(slide, Inches(0.5), Inches(2.2), Inches(3.8), "Respuestas", responses_queryset.count(), PPTXStyleConfig.COLOR_PRIMARY)
        builder.draw_kpi_card(slide, Inches(4.5), Inches(2.2), Inches(3.8), "Satisfacción", f"{(kwargs.get('kpi_satisfaction_avg') or 0):.1f}", RGBColor(31, 41, 55))
        nps_val = nps_data.get('score') if isinstance(nps_data, dict) else None
        builder.draw_kpi_card(slide, Inches(8.5), Inches(2.2), Inches(3.8), "NPS", f"{nps_val if nps_val is not None else '--'}", RGBColor(16, 185, 129))

        # NPS Donut if available
        try:
            nps_img_b64 = nps_data.get('chart_image') if isinstance(nps_data, dict) else None
            if nps_img_b64:
                img_stream = io.BytesIO(base64.b64decode(nps_img_b64))
                slide.shapes.add_picture(img_stream, Inches(4.5), Inches(4.5), height=Inches(2.8))
        except Exception:
            pass

        # SLIDE 3: Heatmap de Correlaciones (si está disponible)
        if heatmap_image:
            try:
                slide = builder.add_slide()
                builder.apply_header(slide, "Mapa de Correlaciones")
                
                # Texto explicativo
                tb_exp = slide.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(12.3), Inches(1))
                tf_exp = tb_exp.text_frame
                tf_exp.word_wrap = True
                p_exp = tf_exp.paragraphs[0]
                p_exp.text = "Este mapa de calor muestra las relaciones entre variables numéricas de la encuesta. Valores cercanos a +1 indican correlación positiva fuerte, -1 correlación negativa fuerte, y 0 ausencia de relación. Identifica patrones para estrategias segmentadas."
                p_exp.font.size = Pt(13)
                p_exp.alignment = PP_ALIGN.JUSTIFY
                p_exp.font.color.rgb = PPTXStyleConfig.COLOR_MUTED
                
                # Insertar heatmap
                hm_stream = io.BytesIO(base64.b64decode(heatmap_image))
                slide.shapes.add_picture(hm_stream, Inches(1.5), Inches(2.8), height=Inches(4))
            except Exception:
                pass

        # SLIDE 3+: PREGUNTAS INDIVIDUALES
        for item in analysis_data:
            slide = builder.add_slide()
            builder.apply_header(slide, f"{item['order']}. {item['text']}")
            
            # --- LAYOUT DE 2 COLUMNAS ---
            # Columna Izquierda: Texto (Insight + Recomendaciones)
            # Columna Derecha: Visual (Gráfico + Tabla)
            
            left_col_x = Inches(0.5)
            left_col_w = Inches(6.0)
            
            right_col_x = Inches(6.8)
            right_col_w = Inches(6.0)
            
            current_y_left = Inches(1.5)
            current_y_right = Inches(1.5)

            # --- COLUMNA IZQUIERDA: ANÁLISIS ---
            
            # 1. Caja de "Insight"
            if item.get('insight'):
                clean_ins = re.sub(r'<[^>]+>', '', item['insight']).replace('&nbsp;', ' ')
                
                # Fondo azul claro
                bg_ins = slide.shapes.add_shape(
                    MSO_SHAPE.RECTANGLE, 
                    left_col_x, current_y_left, left_col_w, Inches(2.5)
                )
                bg_ins.fill.solid()
                bg_ins.fill.fore_color.rgb = RGBColor(239, 246, 255)
                bg_ins.line.color.rgb = RGBColor(191, 219, 254)
                
                # Texto
                tb_ins = slide.shapes.add_textbox(left_col_x + Inches(0.1), current_y_left + Inches(0.1), left_col_w - Inches(0.2), Inches(2.3))
                tf_ins = tb_ins.text_frame
                tf_ins.word_wrap = True
                p = tf_ins.paragraphs[0]
                p.text = f"ANÁLISIS: {clean_ins}"
                p.font.size = Pt(13) # Reducir un poco para asegurar fit
                p.font.color.rgb = RGBColor(30, 58, 138)
                p.alignment = PP_ALIGN.JUSTIFY

                current_y_left += Inches(2.7)

            # 2. Recomendaciones
            recommendations = item.get('recommendations', [])
            if recommendations:
                # Fondo verde claro
                bg_rec = slide.shapes.add_shape(
                    MSO_SHAPE.RECTANGLE, 
                    left_col_x, current_y_left, left_col_w, Inches(2.0)
                )
                bg_rec.fill.solid()
                bg_rec.fill.fore_color.rgb = RGBColor(240, 253, 244)
                bg_rec.line.color.rgb = RGBColor(34, 197, 94)
                bg_rec.line.width = Pt(2)

                tb_rec = slide.shapes.add_textbox(left_col_x + Inches(0.1), current_y_left + Inches(0.1), left_col_w - Inches(0.2), Inches(1.8))
                tf_rec = tb_rec.text_frame
                tf_rec.word_wrap = True
                p_rec = tf_rec.paragraphs[0]
                p_rec.text = "RECOMENDACIONES:"
                p_rec.font.bold = True
                p_rec.font.size = Pt(12)
                p_rec.font.color.rgb = RGBColor(21, 128, 61)
                
                for rec in recommendations[:4]:  # Permitir hasta 4 bullets ahora que hay espacio vertical
                    p = tf_rec.add_paragraph()
                    p.text = f"• {rec}"
                    p.font.size = Pt(11)
                    p.font.color.rgb = RGBColor(22, 101, 52)
                    p.space_after = Pt(5)
                
                current_y_left += Inches(2.2)

            # --- COLUMNA DERECHA: VISUALES ---

            # 3. Gráfico
            if item.get('chart_image'):
                try:
                    img_data = base64.b64decode(item['chart_image'])
                    img_stream = io.BytesIO(img_data)
                    
                    # Insertar imagen ajustada a la columna derecha
                    pic = slide.shapes.add_picture(img_stream, right_col_x, current_y_right, width=right_col_w)
                    
                    # Calcular nueva Y basada en el aspect ratio de la imagen insertada
                    # (python-pptx mantiene aspect ratio si solo das width)
                    current_y_right += pic.height + Inches(0.2)
                            
                except Exception as e:
                    print(f"Error insertando gráfico PPTX: {e}")

            # 4. Tabla de Datos (Debajo del gráfico si hay espacio)
            if (item.get('options') or item.get('chart_labels')) and current_y_right < Inches(6.5):
                tb_opt = slide.shapes.add_textbox(right_col_x, current_y_right, right_col_w, Inches(2))
                tf_opt = tb_opt.text_frame
                p_h = tf_opt.paragraphs[0]
                p_h.text = "Resumen de Datos (Top 5)"
                p_h.font.bold = True
                p_h.font.size = Pt(11)
                p_h.font.color.rgb = PPTXStyleConfig.COLOR_MUTED
                p_h.space_after = Pt(5)
                
                labels = item.get('chart_labels', [])
                values = item.get('chart_data', [])
                
                limit = min(len(labels), 5)
                for i in range(limit):
                    p = tf_opt.add_paragraph()
                    val = values[i]
                    lbl = labels[i]
                    p.text = f"• {lbl}: {val}"
                    p.font.size = Pt(10)
                    p.space_after = Pt(2)

        f = io.BytesIO()
        prs.save(f)
        f.seek(0)
        return f