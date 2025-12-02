"""
PowerPoint Report Generator using python-pptx.
Generador profesional de reportes en formato PPTX con diseño moderno.
Version: 2.0 - Professional Edition
"""
import io
import os
import base64
import re
from datetime import datetime
from django.conf import settings
from django.db.models import Min

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

from surveys.models import QuestionResponse


class PPTXStyleConfig:
    """Configuración profesional de estilos para presentaciones."""
    
    # Paleta de colores corporativos Byteneko
    BYTE_BLUE = RGBColor(13, 110, 253)          # Azul principal
    BYTE_DARK_BLUE = RGBColor(10, 88, 202)      # Azul oscuro
    BYTE_TEXT = RGBColor(17, 24, 39)            # Texto principal
    BYTE_TEXT_LIGHT = RGBColor(55, 65, 81)      # Texto secundario
    BYTE_GRAY = RGBColor(107, 114, 129)         # Gris medio
    BYTE_LIGHT_GRAY = RGBColor(156, 163, 175)   # Gris claro
    BYTE_BG_CARD = RGBColor(248, 249, 250)      # Fondo de tarjetas
    BYTE_BG_LIGHT = RGBColor(249, 250, 251)     # Fondo alternativo
    BYTE_BORDER = RGBColor(222, 226, 230)       # Bordes
    BYTE_GREEN = RGBColor(15, 118, 110)         # Verde principal
    BYTE_SUCCESS = RGBColor(16, 185, 129)       # Verde éxito
    BYTE_WARNING = RGBColor(239, 68, 68)        # Rojo advertencia
    BYTE_ORANGE = RGBColor(249, 115, 22)        # Naranja
    BYTE_PURPLE = RGBColor(139, 92, 246)        # Púrpura
    BYTE_ACCENT = RGBColor(236, 72, 153)        # Rosa acento
    
    # Dimensiones de diapositivas (16:9 - Formato estándar corporativo)
    SLIDE_WIDTH = Inches(10)
    SLIDE_HEIGHT = Inches(7.5)


class PPTXSlideBuilder:
    """Constructor profesional de diapositivas PowerPoint con diseño moderno."""
    
    def __init__(self, presentation):
        self.prs = presentation
        self.logo_path = os.path.join(settings.BASE_DIR, 'static', 'img', 'favicon.ico')
        self.has_logo = os.path.exists(self.logo_path)
        self.style = PPTXStyleConfig
    
    def apply_header(self, slide, title_text):
        """Aplica encabezado profesional con gradiente y sombra a una diapositiva."""
        bar_height = Inches(0.95)
        
        # Barra principal con diseño profesional
        bar = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, 0, 0, 
            self.prs.slide_width, bar_height
        )
        bar.fill.solid()
        bar.fill.fore_color.rgb = self.style.BYTE_BLUE
        bar.line.fill.background()
        
        # Sombra sutil en la barra
        bar.shadow.inherit = False
        
        # Línea de acento inferior más delgada y elegante
        accent = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, 0, Inches(0.92),
            self.prs.slide_width, Inches(0.03)
        )
        accent.fill.solid()
        accent.fill.fore_color.rgb = self.style.BYTE_GREEN
        accent.line.fill.background()
        
        # Título con mejor tipografía
        tb = slide.shapes.add_textbox(Inches(0.6), Inches(0.18), Inches(7.5), Inches(0.6))
        tf = tb.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = title_text
        p.font.color.rgb = RGBColor(255, 255, 255)
        p.font.size = Pt(26)
        p.font.bold = True
        p.font.name = 'Segoe UI'
        
        # Logo o marca corporativa
        if self.has_logo:
            try:
                pic_height = Inches(0.6)
                top_pos = (bar_height - pic_height) / 2
                slide.shapes.add_picture(
                    self.logo_path,
                    self.prs.slide_width - Inches(1.5),
                    top_pos,
                    height=pic_height
                )
            except:
                self._add_text_logo(slide, bar_height)
        else:
            self._add_text_logo(slide, bar_height)
    
    def _add_text_logo(self, slide, bar_height):
        """Agrega logo de texto profesional."""
        tb_logo = slide.shapes.add_textbox(
            self.prs.slide_width - Inches(2.0), 0,
            Inches(1.8), bar_height
        )
        tf_logo = tb_logo.text_frame
        tf_logo.vertical_anchor = MSO_ANCHOR.MIDDLE
        p_logo = tf_logo.paragraphs[0]
        p_logo.text = "BYTENEKO"
        p_logo.font.color.rgb = RGBColor(255, 255, 255)
        p_logo.font.bold = True
        p_logo.font.size = Pt(18)
        p_logo.font.name = 'Segoe UI'
        p_logo.alignment = PP_ALIGN.RIGHT
    
    def add_footer(self, slide, page_number, total_pages, date_range_label):
        """Agrega pie de página profesional con separadores visuales."""
        footer_y = self.prs.slide_height - Inches(0.48)
        
        # Línea superior sutil
        line = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(0.5),
            footer_y - Inches(0.02),
            self.prs.slide_width - Inches(1.0),
            Inches(0.01)
        )
        line.fill.solid()
        line.fill.fore_color.rgb = self.style.BYTE_BORDER
        line.line.fill.background()
        
        # Texto del pie de página
        tb = slide.shapes.add_textbox(
            Inches(0.5),
            footer_y,
            self.prs.slide_width - Inches(1.0),
            Inches(0.38)
        )
        tf = tb.text_frame
        tf.vertical_anchor = MSO_ANCHOR.TOP
        p = tf.paragraphs[0]
        p.text = f"Pág. {page_number}/{total_pages}  •  {date_range_label}  •  Byteneko Analytics Platform"
        p.font.size = Pt(8.5)
        p.font.color.rgb = self.style.BYTE_GRAY
        p.font.name = 'Segoe UI'
        p.alignment = PP_ALIGN.CENTER
    
    def draw_kpi_card(self, slide, x, y, title, value, color=None, subtitle=None, icon=None):
        """Dibuja una tarjeta KPI profesional con sombra, iconos y diseño moderno."""
        if color is None:
            color = self.style.BYTE_BLUE
        
        value = "--" if value is None else str(value)
        w_card = Inches(2.95)
        h_card = Inches(1.75)
        
        # Sombra profesional
        shadow = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            x + Inches(0.03), y + Inches(0.03),
            w_card, h_card
        )
        shadow.fill.solid()
        shadow.fill.fore_color.rgb = RGBColor(205, 205, 210)
        shadow.line.fill.background()
        
        # Tarjeta principal con borde sutil
        card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w_card, h_card
        )
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(255, 255, 255)
        card.line.color.rgb = self.style.BYTE_BORDER
        card.line.width = Pt(1.2)
        
        # Barra de acento superior
        accent_bar = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            x, y,
            w_card, Inches(0.07)
        )
        accent_bar.fill.solid()
        accent_bar.fill.fore_color.rgb = color
        accent_bar.line.fill.background()
        
        # Título del KPI
        tb_title = slide.shapes.add_textbox(x + Inches(0.18), y + Inches(0.18), w_card - Inches(0.36), Inches(0.38))
        tf_title = tb_title.text_frame
        tf_title.vertical_anchor = MSO_ANCHOR.TOP
        p1 = tf_title.paragraphs[0]
        p1.text = title.upper()
        p1.font.size = Pt(10.5)
        p1.font.bold = True
        p1.font.color.rgb = self.style.BYTE_GRAY
        p1.font.name = 'Segoe UI'
        p1.alignment = PP_ALIGN.LEFT
        
        # Valor principal
        tb_val = slide.shapes.add_textbox(x + Inches(0.18), y + Inches(0.62), w_card - Inches(0.36), Inches(0.75))
        tf_val = tb_val.text_frame
        tf_val.vertical_anchor = MSO_ANCHOR.MIDDLE
        p2 = tf_val.paragraphs[0]
        p2.text = value
        p2.font.size = Pt(38)
        p2.font.bold = True
        p2.font.color.rgb = color
        p2.font.name = 'Segoe UI'
        p2.alignment = PP_ALIGN.LEFT
        
        # Subtítulo opcional
        if subtitle:
            tb_sub = slide.shapes.add_textbox(x + Inches(0.18), y + Inches(1.42), w_card - Inches(0.36), Inches(0.28))
            tf_sub = tb_sub.text_frame
            tf_sub.vertical_anchor = MSO_ANCHOR.BOTTOM
            p_sub = tf_sub.paragraphs[0]
            p_sub.text = subtitle
            p_sub.font.size = Pt(9.5)
            p_sub.font.color.rgb = self.style.BYTE_LIGHT_GRAY
            p_sub.font.name = 'Segoe UI'
            p_sub.alignment = PP_ALIGN.LEFT


class PPTXReportGenerator:
    """Generador principal de reportes PowerPoint."""
    
    @staticmethod
    def _clean_title(title, max_len=60):
        """Limpia y trunca títulos."""
        title = title or ""
        title = title.replace('.csv', '')
        return title if len(title) <= max_len else title[:max_len - 3] + "..."
    
    @staticmethod
    def _split_question_title(texto):
        """Separa título de pregunta de información extra entre paréntesis."""
        texto = texto or ""
        if "(" in texto and ")" in texto:
            base, extra = texto.split("(", 1)
            extra = "(" + extra
        else:
            base, extra = texto, ""
        return base.strip(), extra.strip()
    
    @staticmethod
    def _is_text_like_question(item):
        """Determina si una pregunta es de tipo texto."""
        texto = (item.get('text') or '').lower() # Changed 'texto' to 'text'
        if item.get('type') == 'text': # Changed 'tipo' to 'type'
            return True
        keywords = ['comentario', 'sugerencia', 'observación']
        return any(k in texto for k in keywords)
    
    @staticmethod
    def generate_report(survey, analysis_data, nps_data, heatmap_image,
                       date_range_label, responses_queryset, **kwargs):
        """
        Genera un reporte completo en PowerPoint.
        """
        # Crear presentación
        prs = Presentation()
        prs.slide_width = PPTXStyleConfig.SLIDE_WIDTH
        prs.slide_height = PPTXStyleConfig.SLIDE_HEIGHT
        
        builder = PPTXSlideBuilder(prs)
        
        # Calcular satisfacción promedio y fortalezas/oportunidades
        numeric_scores = []
        sat_sum_10 = 0.0
        sat_q_count = 0
        
        for item in analysis_data:
            avg_val = item.get('avg')
            scale_cap = item.get('scale_cap')
            if avg_val is not None and scale_cap:
                norm_10 = (avg_val / scale_cap) * 10
                numeric_scores.append({
                    'order': item['order'],
                    'text': item['text'],
                    'norm_10': norm_10,
                })
                sat_sum_10 += norm_10
                sat_q_count += 1
        
        avg_sat = round(sat_sum_10 / sat_q_count, 1) if sat_q_count else None
        
        # Identificar fortalezas y oportunidades
        strengths = []
        opportunities = []
        if numeric_scores:
            numeric_desc = sorted(numeric_scores, key=lambda x: x['norm_10'], reverse=True)
            numeric_asc = sorted(numeric_scores, key=lambda x: x['norm_10'])
            strengths = [n for n in numeric_desc if n['norm_10'] >= 8][:3]
            opportunities = [n for n in numeric_asc if n['norm_10'] < 7][:3]
        
        total_pages = 4 + len(analysis_data) + (1 if heatmap_image else 0)
        current_page = 1
        
        # SLIDE 1: Portada
        current_page = PPTXReportGenerator._create_cover_slide(
            prs, builder, survey, date_range_label,
            responses_queryset, current_page, total_pages
        )
        
        # SLIDE 2: Agenda
        current_page = PPTXReportGenerator._create_agenda_slide(
            prs, builder, current_page, total_pages, date_range_label
        )
        
        # SLIDE 3: Resumen Ejecutivo
        current_page = PPTXReportGenerator._create_summary_slide(
            prs, builder, survey, nps_data, avg_sat,
            responses_queryset, date_range_label, current_page, total_pages
        )
        
        # SLIDE 4: Heatmap (si existe)
        if heatmap_image:
            current_page = PPTXReportGenerator._create_heatmap_slide(
                prs, builder, heatmap_image, current_page, total_pages, date_range_label
            )
        
        # SLIDE 5: Conclusiones
        current_page = PPTXReportGenerator._create_conclusions_slide(
            prs, builder, strengths, opportunities, current_page, total_pages, date_range_label
        )
        
        # SLIDES DETALLE: Una por pregunta
        for item in analysis_data:
            current_page = PPTXReportGenerator._create_question_slide(
                prs, builder, item, responses_queryset, 
                current_page, total_pages, date_range_label
            )
        
        # Guardar en BytesIO
        f = io.BytesIO()
        prs.save(f)
        f.seek(0)
        return f
    
    @staticmethod
    def _create_cover_slide(prs, builder, survey, date_range_label,
                           responses_queryset, current_page, total_pages):
        """Crea slide de portada profesional con diseño moderno."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        
        # Fondo con degradado visual simulado con capas
        bg_main = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height
        )
        bg_main.fill.solid()
        bg_main.fill.fore_color.rgb = RGBColor(249, 250, 251)
        bg_main.line.fill.background()
        
        # Barra lateral azul moderna
        side_width = Inches(3.5)
        bg_side = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, 0, 0, side_width, prs.slide_height
        )
        bg_side.fill.solid()
        bg_side.fill.fore_color.rgb = builder.style.BYTE_BLUE
        bg_side.line.fill.background()
        
        # Acento verde en barra lateral
        accent_bar = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, 0, prs.slide_height - Inches(0.15),
            side_width, Inches(0.15)
        )
        accent_bar.fill.solid()
        accent_bar.fill.fore_color.rgb = builder.style.BYTE_GREEN
        accent_bar.line.fill.background()
        
        # Logo si existe
        if builder.has_logo:
            try:
                logo_w = Inches(2.0)
                left_pos = (side_width - logo_w) / 2
                slide.shapes.add_picture(builder.logo_path, left_pos, Inches(1.2), width=logo_w)
            except:
                pass
        
        # Marca de texto en sidebar
        tb_brand = slide.shapes.add_textbox(
            Inches(0.3), prs.slide_height - Inches(1.0),
            side_width - Inches(0.6), Inches(0.6)
        )
        tf_brand = tb_brand.text_frame
        tf_brand.vertical_anchor = MSO_ANCHOR.BOTTOM
        p_brand = tf_brand.paragraphs[0]
        p_brand.text = "BYTENEKO\nANALYTICS"
        p_brand.font.color.rgb = RGBColor(255, 255, 255)
        p_brand.font.bold = True
        p_brand.font.size = Pt(14)
        p_brand.font.name = 'Segoe UI'
        p_brand.alignment = PP_ALIGN.CENTER
        
        # Área derecha con título profesional
        right_area_w = prs.slide_width - side_width
        right_area_start = side_width
        
        # Título principal grande
        titulo_encuesta = PPTXReportGenerator._clean_title(survey.title, max_len=80)
        tb_title = slide.shapes.add_textbox(
            right_area_start + Inches(0.6), Inches(1.9),
            right_area_w - Inches(1.2), Inches(2.6)
        )
        tf_title = tb_title.text_frame
        tf_title.vertical_anchor = MSO_ANCHOR.TOP
        tf_title.word_wrap = True
        
        p = tf_title.paragraphs[0]
        p.text = titulo_encuesta
        p.font.size = Pt(46)
        p.font.bold = True
        p.font.color.rgb = builder.style.BYTE_TEXT
        p.font.name = 'Segoe UI'
        p.alignment = PP_ALIGN.LEFT
        p.line_spacing = 1.08
        
        # Subtítulo elegante
        p_sub = tf_title.add_paragraph()
        p_sub.text = "\nReporte Ejecutivo"
        p_sub.font.size = Pt(22)
        p_sub.font.color.rgb = builder.style.BYTE_BLUE
        p_sub.font.bold = False
        p_sub.font.name = 'Segoe UI Light'
        p_sub.space_before = Pt(18)
        
        # Metadata sin iconos para formalidad
        tb_meta = slide.shapes.add_textbox(
            right_area_start + Inches(0.6), Inches(4.9),
            right_area_w - Inches(1.2), Inches(1.5)
        )
        tf_meta = tb_meta.text_frame
        
        p1 = tf_meta.paragraphs[0]
        p1.text = f"Fecha de Generación: {datetime.now().strftime('%d de %B, %Y')}"
        p1.font.size = Pt(12.5)
        p1.font.color.rgb = builder.style.BYTE_TEXT_LIGHT
        p1.font.name = 'Segoe UI'
        p1.space_after = Pt(9)
        
        p2 = tf_meta.add_paragraph()
        p2.text = f"Periodo Analizado: {date_range_label}"
        p2.font.size = Pt(12.5)
        p2.font.color.rgb = builder.style.BYTE_TEXT_LIGHT
        p2.font.name = 'Segoe UI'
        p2.space_after = Pt(9)
        
        p3 = tf_meta.add_paragraph()
        resp_count = responses_queryset.count()
        p3.text = f"Total de Respuestas: {resp_count:,}"
        p3.font.size = Pt(12.5)
        p3.font.color.rgb = builder.style.BYTE_TEXT_LIGHT
        p3.font.name = 'Segoe UI'
        
        builder.add_footer(slide, current_page, total_pages, date_range_label)
        return current_page + 1
    
    @staticmethod
    def _create_agenda_slide(prs, builder, current_page, total_pages, date_range_label):
        """Crea slide de agenda."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        builder.apply_header(slide, "Agenda del Reporte")
        
        content_margin = Inches(1.5)
        content_width = prs.slide_width - (content_margin * 2)
        tb_agenda = slide.shapes.add_textbox(
            content_margin, Inches(1.9), content_width, Inches(4.2)
        )
        tf_ag = tb_agenda.text_frame
        tf_ag.word_wrap = True
        
        p0 = tf_ag.paragraphs[0]
        p0.text = "Contenido del Análisis"
        p0.font.size = Pt(19)
        p0.font.bold = True
        p0.font.color.rgb = PPTXStyleConfig.BYTE_TEXT
        p0.space_after = Pt(18)
        
        bullets = [
            "Resumen ejecutivo con indicadores clave de desempeño.",
            "Mapa de correlaciones entre variables (heatmap).",
            "Conclusiones estratégicas y oportunidades de mejora.",
            "Análisis detallado por pregunta con visualizaciones."
        ]
        for txt in bullets:
            pb = tf_ag.add_paragraph()
            pb.text = f"•  {txt}"
            pb.font.size = Pt(15.5)
            pb.font.color.rgb = PPTXStyleConfig.BYTE_GRAY
            pb.space_after = Pt(13)
        
        builder.add_footer(slide, current_page, total_pages, date_range_label)
        return current_page + 1
    
    @staticmethod
    def _create_summary_slide(prs, builder, survey, nps_data, avg_sat,
                             responses_queryset, date_range_label, current_page, total_pages):
        """Crea slide de resumen ejecutivo profesional con KPIs destacados."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        builder.apply_header(slide, "Resumen Ejecutivo")
        
        # Configuración de layout optimizado
        margin_x = Inches(0.6)
        content_width = prs.slide_width - (margin_x * 2)
        
        # Descripción contextual en tarjeta
        y_context = Inches(1.15)
        h_context = Inches(0.75)
        
        card_context = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, margin_x, y_context, content_width, h_context
        )
        card_context.fill.solid()
        card_context.fill.fore_color.rgb = builder.style.BYTE_BG_LIGHT
        card_context.line.color.rgb = builder.style.BYTE_BORDER
        card_context.line.width = Pt(0.8)
        
        first_response_dt = responses_queryset.aggregate(first=Min('created_at'))['first']
        raw_desc = (getattr(survey, "description", "") or "").strip()
        
        description_text = raw_desc if raw_desc else (
            f"Encuesta recopilada desde {first_response_dt.date().isoformat()}" if first_response_dt
            else "Sin descripción disponible"
        )
        
        tb_context = slide.shapes.add_textbox(
            margin_x + Inches(0.22), y_context + Inches(0.14),
            content_width - Inches(0.44), h_context - Inches(0.28)
        )
        tf_context = tb_context.text_frame
        tf_context.word_wrap = True
        tf_context.vertical_anchor = MSO_ANCHOR.MIDDLE
        
        p_label = tf_context.paragraphs[0]
        p_label.text = "Contexto: "
        p_label.font.bold = True
        p_label.font.size = Pt(11.5)
        p_label.font.color.rgb = builder.style.BYTE_BLUE
        p_label.font.name = 'Segoe UI'
        
        run = p_label.add_run()
        run.text = description_text
        run.font.bold = False
        run.font.size = Pt(10.5)
        run.font.color.rgb = builder.style.BYTE_TEXT_LIGHT
        run.font.name = 'Segoe UI'
        
        # KPIs en grid profesional
        y_kpis = Inches(2.1)
        card_w = Inches(2.95)
        gap = Inches(0.28)
        
        # Calcular posición centrada para 3 KPIs
        total_kpi_width = (card_w * 3) + (gap * 2)
        start_x = (prs.slide_width - total_kpi_width) / 2
        
        # KPI 1: Total Respuestas
        builder.draw_kpi_card(
            slide, start_x, y_kpis,
            "Total Respuestas", 
            responses_queryset.count(),
            color=builder.style.BYTE_BLUE,
            subtitle="Participantes"
        )
        
        # KPI 2: NPS Global
        nps_score = nps_data.get('score')
        nps_text = "--" if nps_score is None else f"{nps_score:.0f}"
        nps_color = builder.style.BYTE_BLUE
        if nps_score is not None:
            if nps_score >= 50:
                nps_color = builder.style.BYTE_SUCCESS
            elif nps_score < 0:
                nps_color = builder.style.BYTE_WARNING
        
        builder.draw_kpi_card(
            slide, start_x + card_w + gap, y_kpis,
            "NPS Score",
            nps_text,
            color=nps_color,
            subtitle="Net Promoter Score"
        )
        
        # KPI 3: Satisfacción Promedio
        avg_sat_text = "--" if avg_sat is None else f"{avg_sat:.1f}"
        builder.draw_kpi_card(
            slide, start_x + (card_w + gap) * 2, y_kpis,
            "Satisfacción",
            avg_sat_text,
            color=builder.style.BYTE_GREEN,
            subtitle="Promedio sobre 10"
        )
        
        # Gráfico de distribución NPS (si existe)
        if nps_data.get('breakdown_chart'):
            y_chart_section = Inches(4.2)
            
            # Título del gráfico
            tb_chart_title = slide.shapes.add_textbox(
                margin_x, y_chart_section, content_width, Inches(0.3)
            )
            p_chart = tb_chart_title.text_frame.paragraphs[0]
            p_chart.text = "Distribución de Sentimiento (Promotores vs Detractores)"
            p_chart.alignment = PP_ALIGN.CENTER
            p_chart.font.size = Pt(11.5)
            p_chart.font.bold = True
            p_chart.font.color.rgb = builder.style.BYTE_TEXT
            p_chart.font.name = 'Segoe UI'
            
            # Imagen del gráfico
            chart_img = io.BytesIO(base64.b64decode(nps_data['breakdown_chart']))
            chart_h = Inches(2.3)
            chart_w = chart_h * 1.8  # Aspecto 16:9 aprox
            chart_x = (prs.slide_width - chart_w) / 2
            chart_y = y_chart_section + Inches(0.4)
            
            slide.shapes.add_picture(chart_img, chart_x, chart_y, width=chart_w, height=chart_h)
        
        builder.add_footer(slide, current_page, total_pages, date_range_label)
        return current_page + 1
    
    @staticmethod
    def _create_heatmap_slide(prs, builder, heatmap_image, current_page, total_pages, date_range_label):
        """Crea slide de heatmap."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        builder.apply_header(slide, "Mapa de calor (Correlaciones)")
        
        img = io.BytesIO(base64.b64decode(heatmap_image))
        margin = Inches(0.8)
        available_w = prs.slide_width - (margin * 2)
        img_w = available_w * 0.6
        img_x = margin
        img_y = Inches(1.8)
        slide.shapes.add_picture(img, img_x, img_y, width=img_w)
        
        # Explicación
        text_x = img_x + img_w + Inches(0.5)
        text_w = available_w * 0.35
        tb = slide.shapes.add_textbox(text_x, Inches(2.5), text_w, Inches(3.0))
        tf = tb.text_frame
        tf.word_wrap = True
        p1 = tf.paragraphs[0]
        p1.text = "¿Cómo leer esto?"
        p1.font.size = Pt(16)
        p1.font.bold = True
        p1.font.color.rgb = PPTXStyleConfig.BYTE_BLUE
        p2 = tf.add_paragraph()
        p2.text = (
            "Este gráfico muestra qué preguntas están relacionadas.\n\n"
            "• Rojo (cerca de 1): Si una sube, la otra también.\n"
            "• Azul (cerca de -1): Relación inversa.\n"
        )
        p2.font.size = Pt(12)
        p2.font.color.rgb = PPTXStyleConfig.BYTE_TEXT
        
        builder.add_footer(slide, current_page, total_pages, date_range_label)
        return current_page + 1
    
    @staticmethod
    def _create_conclusions_slide(prs, builder, strengths, opportunities, 
                                  current_page, total_pages, date_range_label):
        """Crea slide de conclusiones."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        builder.apply_header(slide, "Conclusiones y oportunidades")
        
        col_margin = Inches(0.8)
        col_gap = Inches(0.6)
        col_w = (prs.slide_width - (col_margin * 2) - col_gap) / 2
        col_y = Inches(1.5)
        col_h = Inches(4.8)
        
        # Columna Fortalezas
        bg1 = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, col_margin, col_y, col_w, col_h
        )
        bg1.fill.solid()
        bg1.fill.fore_color.rgb = PPTXStyleConfig.BYTE_BG_CARD
        bg1.line.color.rgb = PPTXStyleConfig.BYTE_BLUE
        bg1.line.width = Pt(2)
        
        tb1 = slide.shapes.add_textbox(
            col_margin + Inches(0.2), col_y + Inches(0.2),
            col_w - Inches(0.4), col_h - Inches(0.4)
        )
        tf1 = tb1.text_frame
        p_t1 = tf1.paragraphs[0]
        p_t1.text = "Top Fortalezas"
        p_t1.font.bold = True
        p_t1.font.size = Pt(18)
        p_t1.font.color.rgb = PPTXStyleConfig.BYTE_BLUE
        p_t1.alignment = PP_ALIGN.CENTER
        p_t1.space_after = Pt(15)
        
        if strengths:
            for s in strengths:
                p = tf1.add_paragraph()
                p.text = f"• P{s['order']}: {PPTXReportGenerator._clean_title(s['text'], 45)}"
                p.font.bold = True
                p.font.size = Pt(12)
                p.space_before = Pt(10)
                p_score = tf1.add_paragraph()
                p_score.text = f"   Puntaje: {s['norm_10']:.1f}/10"
                p_score.font.size = Pt(12)
                p_score.font.color.rgb = PPTXStyleConfig.BYTE_GRAY
        else:
            p = tf1.add_paragraph()
            p.text = "Faltan datos para identificar fortalezas."
            p.alignment = PP_ALIGN.CENTER
        
        # Columna Oportunidades
        x_col2 = col_margin + col_w + col_gap
        bg2 = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, x_col2, col_y, col_w, col_h
        )
        bg2.fill.solid()
        bg2.fill.fore_color.rgb = PPTXStyleConfig.BYTE_BG_CARD
        bg2.line.color.rgb = RGBColor(220, 38, 38)
        bg2.line.width = Pt(2)
        
        tb2 = slide.shapes.add_textbox(
            x_col2 + Inches(0.2), col_y + Inches(0.2),
            col_w - Inches(0.4), col_h - Inches(0.4)
        )
        tf2 = tb2.text_frame
        p_t2 = tf2.paragraphs[0]
        p_t2.text = "Áreas de Mejora"
        p_t2.font.bold = True
        p_t2.font.size = Pt(18)
        p_t2.font.color.rgb = RGBColor(220, 38, 38)
        p_t2.alignment = PP_ALIGN.CENTER
        p_t2.space_after = Pt(15)
        
        if opportunities:
            for o in opportunities:
                p = tf2.add_paragraph()
                p.text = f"• P{o['order']}: {PPTXReportGenerator._clean_title(o['text'], 45)}"
                p.font.bold = True
                p.font.size = Pt(12)
                p.space_before = Pt(10)
                p_score = tf2.add_paragraph()
                p_score.text = f"   Puntaje: {o['norm_10']:.1f}/10"
                p_score.font.size = Pt(12)
                p_score.font.color.rgb = PPTXStyleConfig.BYTE_GRAY
        else:
            p = tf2.add_paragraph()
            p.text = "No se detectan áreas críticas."
            p.alignment = PP_ALIGN.CENTER
        
        builder.add_footer(slide, current_page, total_pages, date_range_label)
        return current_page + 1
    
    @staticmethod
    def _create_question_slide(prs, builder, item, responses_queryset,
                              current_page, total_pages, date_range_label):
        """Crea slide de detalle de pregunta."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        
        base_title, extra = PPTXReportGenerator._split_question_title(item['text'])
        header_title = f"P{item['order']}. {PPTXReportGenerator._clean_title(base_title)}"
        builder.apply_header(slide, header_title)
        
        # Título completo si es necesario
        if extra or len(base_title) > 50:
            full_text = (base_title + " " + extra).strip()
            tb_full = slide.shapes.add_textbox(Inches(0.6), Inches(1.1), Inches(12), Inches(0.5))
            p_full = tb_full.text_frame.paragraphs[0]
            p_full.text = full_text
            p_full.font.color.rgb = PPTXStyleConfig.BYTE_GRAY
            p_full.font.italic = True
            p_full.font.size = Pt(11)
        
        text_like = PPTXReportGenerator._is_text_like_question(item)
        content_start_y = Inches(1.6)
        
        if item['chart_image'] and not text_like:
            # Layout con gráfico
            margin = Inches(0.6)
            gap = Inches(0.4)
            w_chart_area = Inches(7.5)
            h_chart_area = Inches(4.8)
            
            # Fondo del gráfico
            bg_chart = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE, margin, content_start_y, w_chart_area, h_chart_area
            )
            bg_chart.fill.solid()
            bg_chart.fill.fore_color.rgb = RGBColor(252, 252, 253)
            bg_chart.line.color.rgb = PPTXStyleConfig.BYTE_BORDER
            
            # Imagen del gráfico
            img = io.BytesIO(base64.b64decode(item['chart_image']))
            slide.shapes.add_picture(
                img, margin + Inches(0.2), content_start_y + Inches(0.2),
                width=w_chart_area - Inches(0.4)
            )
            
            # Panel de análisis
            x_panel = margin + w_chart_area + gap
            w_panel = prs.slide_width - x_panel - margin
            
            card_h = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE, x_panel, content_start_y, w_panel, h_chart_area
            )
            card_h.fill.solid()
            card_h.fill.fore_color.rgb = RGBColor(255, 255, 255)
            card_h.line.color.rgb = PPTXStyleConfig.BYTE_BLUE
            
            tb_h = slide.shapes.add_textbox(
                x_panel + Inches(0.2), content_start_y + Inches(0.2),
                w_panel - Inches(0.4), h_chart_area - Inches(0.4)
            )
            tf_h = tb_h.text_frame
            tf_h.word_wrap = True
            
            p_t = tf_h.paragraphs[0]
            p_t.text = "Análisis"
            p_t.font.bold = True
            p_t.font.color.rgb = PPTXStyleConfig.BYTE_BLUE
            p_t.font.size = Pt(14)
            p_t.space_after = Pt(10)
            
            clean_insight = re.sub(r'<[^>]+>', '', item['insight']) or "Sin datos relevantes."
            p_ins = tf_h.add_paragraph()
            p_ins.text = clean_insight
            p_ins.font.size = Pt(12)
            p_ins.space_after = Pt(20)
            
            if item.get('top_options'):
                p_top = tf_h.add_paragraph()
                p_top.text = "Top Respuestas:"
                p_top.font.bold = True
                p_top.font.size = Pt(12)
                for l, v in item['top_options']:
                    p_opt = tf_h.add_paragraph()
                    p_opt.text = f"• {l} ({v})"
                    p_opt.font.size = Pt(11)
        
        else:
            # Layout para preguntas de texto
            margin_text = Inches(1.5)
            w_text_area = prs.slide_width - (margin_text * 2)
            tb_t = slide.shapes.add_textbox(margin_text, content_start_y, w_text_area, Inches(4.5))
            tf_t = tb_t.text_frame
            
            p_head = tf_t.paragraphs[0]
            p_head.text = "Resumen de respuestas abiertas"
            p_head.font.bold = True
            p_head.font.size = Pt(16)
            p_head.font.color.rgb = PPTXStyleConfig.BYTE_BLUE
            p_head.alignment = PP_ALIGN.CENTER
            p_head.space_after = Pt(20)
            
            insight_text = re.sub(r'<[^>]+>', '', item['insight'])
            p_body = tf_t.add_paragraph()
            p_body.text = insight_text
            p_body.alignment = PP_ALIGN.CENTER
            p_body.font.size = Pt(14)
            
            # Obtener comentarios literales
            comentarios = QuestionResponse.objects.filter(
                question_id=item['id'],
                survey_response__in=responses_queryset,
                text_value__isnull=False
            ).exclude(text_value__exact="")
            
            comentarios = comentarios.select_related('survey_response').order_by(
                '-survey_response__created_at'
            )[:3]
            
            if comentarios:
                p_ex = tf_t.add_paragraph()
                p_ex.text = "\nAlgunos comentarios literales:"
                p_ex.font.bold = True
                p_ex.font.color.rgb = PPTXStyleConfig.BYTE_GRAY
                p_ex.space_before = Pt(20)
                
                for c in comentarios:
                    p_c = tf_t.add_paragraph()
                    p_c.text = f'"{(c.text_value or "").strip()}"'
                    p_c.font.italic = True
                    p_c.font.size = Pt(12)
                    p_c.space_before = Pt(5)
        
        builder.add_footer(slide, current_page, total_pages, date_range_label)
        return current_page + 1