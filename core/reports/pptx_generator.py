"""
PowerPoint Report Generator using python-pptx.
Maneja toda la lógica de creación de presentaciones.
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
    """Configuración de estilos para presentaciones."""
    
    # Colores de marca
    BYTE_BLUE = RGBColor(13, 110, 253)
    BYTE_TEXT = RGBColor(17, 24, 39)
    BYTE_GRAY = RGBColor(107, 114, 129)
    BYTE_BG_CARD = RGBColor(248, 249, 250)
    BYTE_BORDER = RGBColor(222, 226, 230)
    BYTE_GREEN = RGBColor(15, 118, 110)
    BYTE_SUCCESS = RGBColor(16, 185, 129)
    BYTE_WARNING = RGBColor(239, 68, 68)
    
    # Dimensiones de diapositivas (16:9)
    SLIDE_WIDTH = Inches(13.333)
    SLIDE_HEIGHT = Inches(7.5)


class PPTXSlideBuilder:
    """Constructor de diapositivas PowerPoint."""
    
    def __init__(self, presentation):
        self.prs = presentation
        self.logo_path = os.path.join(settings.BASE_DIR, 'static', 'img', 'favicon.ico')
        self.has_logo = os.path.exists(self.logo_path)
    
    def apply_header(self, slide, title_text):
        """Aplica encabezado estándar a una diapositiva."""
        bar_height = Inches(1.0)
        
        # Barra principal
        bar = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, 0, 0, 
            self.prs.slide_width, bar_height
        )
        bar.fill.solid()
        bar.fill.fore_color.rgb = PPTXStyleConfig.BYTE_BLUE
        bar.line.fill.background()
        
        # Línea de acento
        accent = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, 0, Inches(0.96),
            self.prs.slide_width, Inches(0.04)
        )
        accent.fill.solid()
        accent.fill.fore_color.rgb = PPTXStyleConfig.BYTE_GREEN
        accent.line.fill.background()
        
        # Título
        tb = slide.shapes.add_textbox(Inches(0.6), Inches(0), Inches(10), bar_height)
        tf = tb.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.text = title_text
        p.font.color.rgb = RGBColor(255, 255, 255)
        p.font.size = Pt(24)
        p.font.bold = True
        
        # Logo o texto
        if self.has_logo:
            try:
                pic_height = Inches(0.6)
                top_pos = (bar_height - pic_height) / 2
                slide.shapes.add_picture(
                    self.logo_path,
                    self.prs.slide_width - Inches(2.0),
                    top_pos,
                    height=pic_height
                )
            except:
                pass
        else:
            tb_logo = slide.shapes.add_textbox(
                self.prs.slide_width - Inches(2.5), 0,
                Inches(2.0), bar_height
            )
            tf_logo = tb_logo.text_frame
            tf_logo.vertical_anchor = MSO_ANCHOR.MIDDLE
            p_logo = tf_logo.paragraphs[0]
            p_logo.text = "BYTENEKO"
            p_logo.font.color.rgb = RGBColor(255, 255, 255)
            p_logo.font.bold = True
            p_logo.alignment = PP_ALIGN.RIGHT
    
    def add_footer(self, slide, page_number, total_pages, date_range_label):
        """Agrega pie de página a una diapositiva."""
        tb = slide.shapes.add_textbox(
            Inches(0.6),
            self.prs.slide_height - Inches(0.45),
            self.prs.slide_width - Inches(1.2),
            Inches(0.3)
        )
        tf = tb.text_frame
        tf.vertical_anchor = MSO_ANCHOR.BOTTOM
        p = tf.paragraphs[0]
        p.text = f"Página {page_number} de {total_pages} • {date_range_label} • Byteneko Analytics v1.0"
        p.font.size = Pt(9)
        p.font.color.rgb = PPTXStyleConfig.BYTE_GRAY
        p.alignment = PP_ALIGN.LEFT
    
    def draw_kpi_card(self, slide, x, y, title, value, color=None, subtitle=None):
        """Dibuja una tarjeta KPI."""
        if color is None:
            color = PPTXStyleConfig.BYTE_BLUE
        
        value = "--" if value is None else str(value)
        w_card = Inches(3.6)
        h_card = Inches(1.9)
        
        # Sombra
        shadow = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            x + Inches(0.05), y + Inches(0.05),
            w_card, h_card
        )
        shadow.fill.solid()
        shadow.fill.fore_color.rgb = RGBColor(210, 210, 210)
        shadow.line.fill.background()
        
        # Tarjeta
        card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w_card, h_card
        )
        card.fill.solid()
        card.fill.fore_color.rgb = PPTXStyleConfig.BYTE_BG_CARD
        card.line.color.rgb = PPTXStyleConfig.BYTE_BORDER
        
        # Título
        tb_title = slide.shapes.add_textbox(x, y + Inches(0.15), w_card, Inches(0.4))
        tf_title = tb_title.text_frame
        tf_title.vertical_anchor = MSO_ANCHOR.TOP
        p1 = tf_title.paragraphs[0]
        p1.text = title
        p1.font.size = Pt(13)
        p1.font.color.rgb = PPTXStyleConfig.BYTE_GRAY
        p1.alignment = PP_ALIGN.CENTER
        
        # Valor
        tb_val = slide.shapes.add_textbox(x, y + Inches(0.4), w_card, Inches(1.0))
        tf_val = tb_val.text_frame
        tf_val.vertical_anchor = MSO_ANCHOR.MIDDLE
        p2 = tf_val.paragraphs[0]
        p2.text = value
        p2.font.size = Pt(36)
        p2.font.bold = True
        p2.font.color.rgb = color
        p2.alignment = PP_ALIGN.CENTER
        
        # Subtítulo
        if subtitle:
            tb_sub = slide.shapes.add_textbox(x, y + Inches(1.4), w_card, Inches(0.4))
            tf_sub = tb_sub.text_frame
            p_sub = tf_sub.paragraphs[0]
            p_sub.text = subtitle
            p_sub.font.size = Pt(10)
            p_sub.font.color.rgb = PPTXStyleConfig.BYTE_GRAY
            p_sub.alignment = PP_ALIGN.CENTER


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
        """Crea slide de portada."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        
        # Barra lateral azul
        side_width = Inches(4.0)
        bg = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, 0, 0, side_width, prs.slide_height
        )
        bg.fill.solid()
        bg.fill.fore_color.rgb = PPTXStyleConfig.BYTE_BLUE
        bg.line.fill.background()
        
        # Logo si existe
        if builder.has_logo:
            try:
                logo_w = Inches(2.5)
                left_pos = (side_width - logo_w) / 2
                slide.shapes.add_picture(builder.logo_path, left_pos, Inches(1.0), width=logo_w)
            except:
                pass
        
        # Área derecha con título
        right_area_w = prs.slide_width - side_width
        right_area_start = side_width
        textbox_h = Inches(4.0)
        textbox_y = (prs.slide_height - textbox_h) / 2
        
        tb_title = slide.shapes.add_textbox(
            right_area_start + Inches(0.5), textbox_y,
            right_area_w - Inches(1.0), textbox_h
        )
        tf_title = tb_title.text_frame
        tf_title.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf_title.word_wrap = True
        
        titulo_encuesta = PPTXReportGenerator._clean_title(survey.title)
        
        p = tf_title.paragraphs[0]
        p.text = titulo_encuesta
        p.font.size = Pt(44)
        p.font.bold = True
        p.font.color.rgb = PPTXStyleConfig.BYTE_TEXT
        p.alignment = PP_ALIGN.LEFT
        
        p_sub = tf_title.add_paragraph()
        p_sub.text = f"\nReporte generado: {datetime.now().strftime('%d/%m/%Y')}"
        p_sub.font.size = Pt(16)
        p_sub.font.color.rgb = PPTXStyleConfig.BYTE_GRAY
        
        p_sub2 = tf_title.add_paragraph()
        p_sub2.text = f"Periodo: {date_range_label}"
        p_sub2.font.size = Pt(16)
        p_sub2.font.color.rgb = PPTXStyleConfig.BYTE_GRAY
        
        # Etiqueta inferior
        tb_tag = slide.shapes.add_textbox(
            right_area_start + Inches(0.5),
            prs.slide_height - Inches(0.8),
            right_area_w - Inches(1.0),
            Inches(0.5)
        )
        p_tag = tb_tag.text_frame.paragraphs[0]
        p_tag.text = "Byteneko Analytics · Reporte automático"
        p_tag.font.size = Pt(11)
        p_tag.font.color.rgb = PPTXStyleConfig.BYTE_GRAY
        p_tag.alignment = PP_ALIGN.RIGHT
        
        builder.add_footer(slide, current_page, total_pages, date_range_label)
        return current_page + 1
    
    @staticmethod
    def _create_agenda_slide(prs, builder, current_page, total_pages, date_range_label):
        """Crea slide de agenda."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        builder.apply_header(slide, "Agenda del reporte")
        
        content_margin = Inches(1.5)
        content_width = prs.slide_width - (content_margin * 2)
        tb_agenda = slide.shapes.add_textbox(
            content_margin, Inches(2.0), content_width, Inches(4.0)
        )
        tf_ag = tb_agenda.text_frame
        tf_ag.word_wrap = True
        
        p0 = tf_ag.paragraphs[0]
        p0.text = "En este reporte encontrarás:"
        p0.font.size = Pt(20)
        p0.font.bold = True
        p0.font.color.rgb = PPTXStyleConfig.BYTE_TEXT
        p0.space_after = Pt(20)
        
        bullets = [
            "Resumen ejecutivo con KPIs clave.",
            "Mapa de relaciones entre variables (heatmap).",
            "Conclusiones clave y principales oportunidades de mejora.",
            "Detalle por pregunta con gráficas y hallazgos específicos."
        ]
        for txt in bullets:
            pb = tf_ag.add_paragraph()
            pb.text = f"•  {txt}"
            pb.font.size = Pt(16)
            pb.font.color.rgb = PPTXStyleConfig.BYTE_GRAY
            pb.space_after = Pt(14)
        
        builder.add_footer(slide, current_page, total_pages, date_range_label)
        return current_page + 1
    
    @staticmethod
    def _create_summary_slide(prs, builder, survey, nps_data, avg_sat,
                             responses_queryset, date_range_label, current_page, total_pages):
        """Crea slide de resumen ejecutivo."""
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        builder.apply_header(slide, "Resumen ejecutivo")
        
        # Configuración de layout
        card_w = Inches(3.5)
        gap = Inches(0.5)
        total_group_w = (card_w * 3) + (gap * 2)
        start_x = (prs.slide_width - total_group_w) / 2
        
        y_desc = Inches(1.3)
        h_desc = Inches(0.9)
        y_kpi = Inches(2.5)
        y_chart_label = Inches(4.6)
        y_chart_img = Inches(4.9)
        h_chart_target = Inches(2.2)
        
        # Descripción
        first_response_dt = responses_queryset.aggregate(first=Min('created_at'))['first']
        description_lines = []
        raw_desc = (getattr(survey, "description", "") or "").strip() # Changed 'descripcion' to 'description' if model allows, or keep original
        # NOTE: Assuming the model has 'description' based on previous files. If it's 'descripcion', change it back.
        # Checking models.py... it has 'description'.
        if raw_desc:
            description_lines.append(raw_desc)
        elif first_response_dt:
            description_lines.append(f"Importada {first_response_dt.date().isoformat()}")
        if not description_lines:
            description_lines.append("Sin descripción disponible.")
        
        card_desc = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, start_x, y_desc, total_group_w, h_desc
        )
        card_desc.fill.solid()
        card_desc.fill.fore_color.rgb = PPTXStyleConfig.BYTE_BG_CARD
        card_desc.line.color.rgb = PPTXStyleConfig.BYTE_BORDER
        
        tb_desc = slide.shapes.add_textbox(
            start_x + Inches(0.2), y_desc, 
            total_group_w - Inches(0.4), h_desc
        )
        tf = tb_desc.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p_label = tf.paragraphs[0]
        p_label.text = "Sobre esta encuesta: "
        p_label.font.bold = True
        p_label.font.size = Pt(12)
        p_label.font.color.rgb = PPTXStyleConfig.BYTE_BLUE
        run = p_label.add_run()
        run.text = " ".join(description_lines)
        run.font.bold = False
        run.font.color.rgb = PPTXStyleConfig.BYTE_TEXT
        
        # KPIs
        builder.draw_kpi_card(slide, start_x, y_kpi, "Total respuestas", responses_queryset.count())
        
        nps_score = nps_data.get('score')
        nps_text = None if nps_score is None else f"{nps_score:.1f}"
        nps_color = PPTXStyleConfig.BYTE_BLUE
        if nps_score is not None:
            if nps_score >= 50:
                nps_color = PPTXStyleConfig.BYTE_SUCCESS
            elif nps_score < 0:
                nps_color = PPTXStyleConfig.BYTE_WARNING
        
        builder.draw_kpi_card(slide, start_x + card_w + gap, y_kpi, "NPS global", nps_text, nps_color)
        
        avg_sat_text = None if avg_sat is None else f"{avg_sat:.1f}"
        builder.draw_kpi_card(slide, start_x + (card_w + gap) * 2, y_kpi, "Satisfacción (/10)", avg_sat_text)
        
        # Gráfico NPS
        if nps_data.get('breakdown_chart'):
            tb_g = slide.shapes.add_textbox(start_x, y_chart_label, total_group_w, Inches(0.3))
            p_g = tb_g.text_frame.paragraphs[0]
            p_g.text = "Distribución de sentimiento"
            p_g.alignment = PP_ALIGN.CENTER
            p_g.font.size = Pt(11)
            p_g.font.bold = True
            p_g.font.color.rgb = PPTXStyleConfig.BYTE_GRAY
            
            chart_img = io.BytesIO(base64.b64decode(nps_data['breakdown_chart']))
            aspect_ratio = 5.0 / 3.0
            chart_width = h_chart_target * aspect_ratio
            chart_x = (prs.slide_width - chart_width) / 2
            slide.shapes.add_picture(chart_img, chart_x, y_chart_img, width=chart_width, height=h_chart_target)
        
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