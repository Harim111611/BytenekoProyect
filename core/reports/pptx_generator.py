# === EXPORT FUNCTION ===
def generate_full_pptx_report(survey, analysis_data, nps_data=None, **kwargs):
    """
    Genera un reporte PPTX completo a partir de los datos de análisis y encuesta.
    Args:
        survey: Objeto encuesta (debe tener al menos .title)
        analysis_data: Lista de análisis de preguntas
        nps_data: Diccionario de datos NPS (opcional)
        kwargs: Otros parámetros opcionales (start_date, end_date, total_responses, kpi_satisfaction_avg, heatmap_image)
    Returns:
        bytes: Archivo PPTX en binario
    """
    generator = PPTXReportGenerator()
    return generator.generate(survey, analysis_data, nps_data, **kwargs)

import io
import base64
import logging
import re
from typing import List, Dict, Any, Optional

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

# IMPORTAR MATPLOTLIB PARA GENERAR GRÁFICAS
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# Config tipográfica global para gráficos
matplotlib.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Calibri", "DejaVu Sans", "Arial"],
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
})

logger = logging.getLogger(__name__)

# ==========================================
# 1. GENERADOR DE GRÁFICAS
# ==========================================
class ChartGenerator:
    
    @staticmethod
    def generate_bar_chart(options: List[Dict], question_text: str = "") -> str:
        """Genera gráfica de barras horizontales profesional."""
        if not options:
            return ""
        
        try:
            valid_options = [opt for opt in options if opt.get('count', 0) > 0]
            if not valid_options:
                logger.warning(f"Sin datos válidos para: {question_text}")
                return ""
            
            # Top 10 opciones
            valid_options = sorted(valid_options, key=lambda x: x.get('count', 0), reverse=True)[:10]
            
            labels = [str(opt.get('label', ''))[:30] for opt in valid_options]
            counts = [opt.get('count', 0) for opt in valid_options]
            
            # Calcular porcentajes si no existen
            total = sum(counts)
            percents = [opt.get('percent', 0) for opt in valid_options]
            if all(p == 0 for p in percents) and total > 0:
                percents = [(c/total)*100 for c in counts]
            
            # Crear figura
            fig, ax = plt.subplots(figsize=(7, max(4, len(labels)*0.4)))
            
            # Invertir para que el mayor esté arriba
            labels.reverse()
            counts.reverse()
            percents.reverse()
            
            y_pos = np.arange(len(labels))
            colors = plt.cm.Blues(np.linspace(0.5, 0.85, len(labels)))
            bars = ax.barh(y_pos, counts, color=colors, edgecolor='white', linewidth=1.5, height=0.7)
            
            # Etiquetas de porcentaje
            max_count = max(counts)
            for i, (bar, pct, cnt) in enumerate(zip(bars, percents, counts)):
                width = bar.get_width()
                label = f'{pct:.1f}%' if pct > 0 else f'{cnt}'
                ax.text(width + max_count*0.015, bar.get_y() + bar.get_height()/2, 
                       label, ha='left', va='center', fontsize=11, fontweight='600', color='#1e293b')
            
            ax.set_yticks(y_pos)
            ax.set_yticklabels(labels, fontsize=10, color='#334155')
            ax.set_xlabel('Respuestas', fontsize=11, fontweight='600', color='#1e293b')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_linewidth(0.5)
            ax.spines['bottom'].set_linewidth(0.5)
            ax.grid(axis='x', alpha=0.2, linestyle='-', linewidth=0.5)
            ax.set_xlim(0, max_count * 1.2)
            
            plt.tight_layout(pad=0.5)
            
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=200, bbox_inches='tight', facecolor='white')
            buffer.seek(0)
            img_b64 = base64.b64encode(buffer.read()).decode()
            plt.close(fig)
            
            logger.info(f"✓ Gráfica de barras generada: {question_text[:50]}")
            return f"data:image/png;base64,{img_b64}"
            
        except Exception as e:
            logger.error(f"Error en gráfica de barras: {e}", exc_info=True)
            return ""
    
    @staticmethod
    def generate_pie_chart(options: List[Dict], question_text: str = "") -> str:
        """Genera gráfica de pastel profesional."""
        if not options:
            return ""
        
        try:
            valid_options = [opt for opt in options if opt.get('count', 0) > 0]
            if not valid_options:
                return ""
            
            valid_options = valid_options[:7]  # Top 7
            
            labels = [str(opt.get('label', ''))[:20] for opt in valid_options]
            counts = [opt.get('count', 0) for opt in valid_options]
            
            fig, ax = plt.subplots(figsize=(7, 5))
            colors = plt.cm.Set3(np.linspace(0, 1, len(labels)))
            
            def autopct_format(pct):
                return f'{pct:.1f}%' if pct > 3 else ''
            
            wedges, texts, autotexts = ax.pie(counts, labels=labels, autopct=autopct_format,
                                               colors=colors, startangle=90,
                                               textprops={'fontsize': 9, 'color': '#1e293b'},
                                               wedgeprops={'edgecolor': 'white', 'linewidth': 1.5})
            
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')
                autotext.set_fontsize(11)
            
            plt.tight_layout()
            
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=200, bbox_inches='tight', facecolor='white')
            buffer.seek(0)
            img_b64 = base64.b64encode(buffer.read()).decode()
            plt.close(fig)
            
            logger.info(f"✓ Gráfica de pastel generada: {question_text[:50]}")
            return f"data:image/png;base64,{img_b64}"
            
        except Exception as e:
            logger.error(f"Error en gráfica de pastel: {e}", exc_info=True)
            return ""
    
    @staticmethod
    def generate_nps_chart(promoters: int, passives: int, detractors: int) -> str:
        """Genera gráfica NPS profesional."""
        try:
            if promoters == 0 and passives == 0 and detractors == 0:
                return ""
            
            labels = ['Promotores\n(9-10)', 'Pasivos\n(7-8)', 'Detractores\n(0-6)']
            values = [promoters, passives, detractors]
            colors = ['#10b981', '#64748b', '#ef4444']
            
            fig, ax = plt.subplots(figsize=(7, 4.5))
            bars = ax.bar(labels, values, color=colors, edgecolor='white', linewidth=2, width=0.65)
            
            max_val = max(values) if values else 1
            for bar, val in zip(bars, values):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2, height + max_val*0.03,
                       f'{val:,}', ha='center', va='bottom', fontsize=14, fontweight='bold', color='#1e293b')
            
            ax.set_ylabel('Cantidad de Respuestas', fontsize=11, fontweight='600', color='#1e293b')
            ax.set_ylim(0, max_val * 1.15)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_linewidth(0.5)
            ax.spines['bottom'].set_linewidth(0.5)
            ax.grid(axis='y', alpha=0.2, linestyle='-', linewidth=0.5)
            ax.tick_params(axis='x', labelsize=10, colors='#334155')
            ax.tick_params(axis='y', labelsize=9, colors='#64748b')
            
            plt.tight_layout()
            
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=200, bbox_inches='tight', facecolor='white')
            buffer.seek(0)
            img_b64 = base64.b64encode(buffer.read()).decode()
            plt.close(fig)
            
            logger.info(f"✓ Gráfica NPS generada")
            return f"data:image/png;base64,{img_b64}"
            
        except Exception as e:
            logger.error(f"Error en gráfica NPS: {e}", exc_info=True)
            return ""
    
    @staticmethod
    def generate_numeric_distribution(values: List[float], question_text: str = "") -> str:
        """Genera histograma para datos numéricos."""
        if not values or len(values) == 0:
            return ""
        
        try:
            fig, ax = plt.subplots(figsize=(7, 4.5))
            
            n_bins = min(25, max(10, int(np.sqrt(len(values)))))
            counts, bins, patches = ax.hist(values, bins=n_bins, color='#3b82f6', 
                                           edgecolor='white', linewidth=1, alpha=0.85)
            
            cm = plt.cm.Blues
            for i, patch in enumerate(patches):
                patch.set_facecolor(cm(0.5 + (i / len(patches)) * 0.35))
            
            mean_val = np.mean(values)
            ax.axvline(mean_val, color='#ef4444', linestyle='--', linewidth=2.5, 
                      label=f'Promedio: {mean_val:.1f}', alpha=0.9)
            
            ax.set_xlabel('Valor', fontsize=11, fontweight='600', color='#1e293b')
            ax.set_ylabel('Frecuencia', fontsize=11, fontweight='600', color='#1e293b')
            ax.legend(fontsize=10, loc='upper right', framealpha=0.95)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_linewidth(0.5)
            ax.spines['bottom'].set_linewidth(0.5)
            ax.grid(axis='y', alpha=0.2, linestyle='-', linewidth=0.5)
            ax.tick_params(labelsize=9, colors='#64748b')
            
            plt.tight_layout()
            
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=200, bbox_inches='tight', facecolor='white')
            buffer.seek(0)
            img_b64 = base64.b64encode(buffer.read()).decode()
            plt.close(fig)
            
            logger.info(f"✓ Histograma generado: {question_text[:50]}")
            return f"data:image/png;base64,{img_b64}"
            
        except Exception as e:
            logger.error(f"Error en histograma: {e}", exc_info=True)
            return ""

# ==========================================
# 2. NORMALIZACIÓN DE DATOS
# ==========================================
class DataNormalizer:
    
    @staticmethod
    def safe_nps_extract(nps_data: Optional[Dict]) -> Dict[str, Any]:
        safe_data = nps_data if isinstance(nps_data, dict) else {}
        
        score = safe_data.get('score')
        promoters = safe_data.get('promoters', 0)
        passives = safe_data.get('passives', 0)
        detractors = safe_data.get('detractors', 0)
        
        if (score is None or score == 0) and (promoters + passives + detractors) > 0:
            total = promoters + passives + detractors
            score = round(((promoters - detractors) / total) * 100, 1) if total > 0 else 0
        
        return {
            'score': score if score is not None else 0,
            'promoters': promoters,
            'passives': passives,
            'detractors': detractors,
            'chart_image': safe_data.get('chart_image'),
        }

# ==========================================
# 3. TEMA
# ==========================================
class Theme:
    PRIMARY = RGBColor(30, 58, 138)
    SECONDARY = RGBColor(59, 130, 246)
    ACCENT = RGBColor(6, 182, 212)
    
    BG_SLIDE = RGBColor(248, 250, 252)
    BG_CARD = RGBColor(255, 255, 255)
    
    TEXT_MAIN = RGBColor(15, 23, 42)
    TEXT_SUB = RGBColor(71, 85, 105)
    TEXT_LIGHT = RGBColor(255, 255, 255)
    TEXT_MUTED = RGBColor(148, 163, 184)

    # NUEVO: tipografía base
    FONT_TITLE = "Calibri"
    FONT_BODY = "Calibri"

# ==========================================
# 4. GENERADOR PPTX
# ==========================================
class PPTXReportGenerator:

    def _set_paragraph_style(
        self,
        p,
        size: int,
        *,
        bold: bool = False,
        italic: bool = False,
        color: Optional[RGBColor] = None,
        align: Optional[int] = None,
        line_spacing: Optional[float] = None,
        font_name: Optional[str] = None,
        max_chars: Optional[int] = 300,
        min_font_size: int = 8,
    ):
        # Truncar texto si es necesario (ya no se trunca agresivamente)
        if hasattr(p, 'text') and max_chars is not None and isinstance(p.text, str):
            if len(p.text) > max_chars * 2: # Solo si es muy largo
                p.text = p.text[:max_chars*2] + '…'
        font = p.font
        font.size = Pt(max(size, min_font_size))
        font.bold = bold
        font.italic = italic
        font.name = font_name or Theme.FONT_BODY
        if color is not None:
            font.color.rgb = color
        if align is not None:
            p.alignment = align
        if line_spacing is not None:
            p.line_spacing = line_spacing

    def _render_text_answers(self, slide, texts):
        """Renderiza comentarios de texto más legibles."""
        if not texts:
            return

        y = Inches(1.6)
        max_boxes = 5
        box_height = Inches(0.95)

        for txt in texts[:max_boxes]:
            clean_txt = self._clean_text(txt)[:180]
            if not clean_txt:
                continue

            box = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(0.7),
                y,
                Inches(7.2),
                box_height
            )
            box.fill.solid()
            box.fill.fore_color.rgb = RGBColor(248, 250, 252)
            box.line.color.rgb = RGBColor(203, 213, 225)
            box.line.width = Pt(1)

            tf = box.text_frame
            tf.word_wrap = True
            tf.shrink_to_fit = True
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf.margin_left = Inches(0.25)
            tf.margin_right = Inches(0.25)
            tf.margin_top = Inches(0.12)
            tf.margin_bottom = Inches(0.12)

            p = tf.paragraphs[0]
            p.text = f"“{clean_txt}”"
            self._set_paragraph_style(
                p,
                size=12,
                italic=True,
                color=Theme.TEXT_MAIN,
                line_spacing=1.25,
                font_name=Theme.FONT_BODY,
            )

            y += box_height + Inches(0.1)

    def _add_heatmap_slide(self, kpi_val, heatmap_img):
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = Theme.BG_SLIDE
        self._add_header(slide, "Mapa de Calor y KPI")

        # KPI
        self._create_card(slide, Inches(0.4), Inches(1.3), Inches(4.2), Inches(5.8))
        tb_label = slide.shapes.add_textbox(Inches(0.6), Inches(1.8), Inches(3.8), Inches(0.7))
        p_l = tb_label.text_frame.paragraphs[0]
        p_l.text = "KPI Promedio"
        p_l.font.size = Pt(18)  # Aumentado de 15 a 18
        p_l.font.bold = True
        p_l.font.color.rgb = Theme.TEXT_SUB
        p_l.alignment = PP_ALIGN.CENTER

        tb = slide.shapes.add_textbox(Inches(0.6), Inches(2.8), Inches(3.8), Inches(1.8))
        tf = tb.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.text = f"{kpi_val:.2f}" if kpi_val else "N/A"
        p.font.size = Pt(72)  # Aumentado de 68 a 72
        p.font.bold = True
        p.font.color.rgb = Theme.ACCENT
        p.alignment = PP_ALIGN.CENTER

        # Heatmap
        self._create_card(slide, Inches(4.8), Inches(1.3), Inches(8.1), Inches(5.8))
        if heatmap_img:
            stream = self._decode_image(heatmap_img)
            if stream:
                try:
                    slide.shapes.add_picture(stream, Inches(5), Inches(1.5), width=Inches(7.7))
                except Exception as e:
                    logger.error(f"Error insertando heatmap: {e}")

    def generate(self, survey, analysis_data, nps_data=None, **kwargs):
        """
        Genera el reporte PPTX completo.
        Args:
            survey: Objeto encuesta (debe tener al menos .title)
            analysis_data: Lista de análisis de preguntas
            nps_data: Diccionario de datos NPS (opcional)
            kwargs: Otros parámetros opcionales (start_date, end_date, total_responses, kpi_satisfaction_avg, heatmap_image)
        Returns:
            bytes: Archivo PPTX en binario
        """
        if analysis_data:
            analysis_data.sort(key=lambda x: x.get('order', 0))

        clean_nps = DataNormalizer.safe_nps_extract(nps_data)

        title = getattr(survey, 'title', 'Reporte de Encuesta')
        dates = f"{kwargs.get('start_date') or ''} - {kwargs.get('end_date') or ''}".strip(' - ')

        logger.info(f"Generando PPTX: {title} | Preguntas: {len(analysis_data)}")

        self._add_cover_slide(title, dates, kwargs.get('total_responses', 0))

        if clean_nps.get('score', 0) != 0 or clean_nps.get('promoters', 0) > 0:
            self._add_nps_slide(clean_nps)

        if kwargs.get('kpi_satisfaction_avg') or kwargs.get('heatmap_image'):
            self._add_heatmap_slide(kwargs.get('kpi_satisfaction_avg', 0), kwargs.get('heatmap_image'))

        if analysis_data:
            for idx, item in enumerate(analysis_data):
                logger.info(f"Procesando slide {idx+1}/{len(analysis_data)}")
                self._add_content_slide(item)

        output = io.BytesIO()
        self.prs.save(output)
        output.seek(0)

        logger.info(f"✓ PPTX generado exitosamente | Tamaño: {len(output.getvalue())/1024:.1f}KB")
        return output.getvalue()

    def __init__(self):
        self.prs = Presentation()
        self.prs.slide_width = Inches(13.333)
        self.prs.slide_height = Inches(7.5)

    def _clean_text(self, text: Any) -> str:
        """Limpia el texto preservando saltos de línea HTML básicos."""
        if text is None: 
            return ""
        text_str = str(text)
        # CORRECCIÓN CRÍTICA: Reemplazar breaks por saltos de línea ANTES de borrar tags
        text_str = re.sub(r'<(br|p|div)[^>]*>', '\n', text_str, flags=re.IGNORECASE)
        # Limpiar resto de tags
        clean = re.sub('<[^<]+?>', '', text_str)
        clean = re.sub(r'\s*-\s*ID:\d+', '', clean)
        return clean.strip()

    def _decode_image(self, b64_string: str):
        if not b64_string:
            return None
        try:
            if "," in b64_string:
                _, data = b64_string.split(",", 1)
            else:
                data = b64_string
            return io.BytesIO(base64.b64decode(data))
        except Exception as e:
            logger.warning(f"Error decodificando imagen: {e}")
            return None

    def _create_card(self, slide, x, y, w, h, shadow=True):
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
        shape.fill.solid()
        shape.fill.fore_color.rgb = Theme.BG_CARD
        shape.line.color.rgb = RGBColor(226, 232, 240)
        shape.line.width = Pt(0.75)
        if shadow:
            shape.shadow.inherit = False
        return shape

    def _add_header(self, slide, title_text):
        # Barra lateral
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.4), Inches(0.35), Inches(0.09), Inches(0.55))
        bar.fill.solid()
        bar.fill.fore_color.rgb = Theme.ACCENT
        bar.line.fill.background()
        
        # Título
        tb = slide.shapes.add_textbox(Inches(0.6), Inches(0.3), Inches(12), Inches(0.9))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = Inches(0.05)
        tf.margin_right = Inches(0.05)

        p = tf.paragraphs[0]
        p.text = self._clean_text(title_text)[:110]
        self._set_paragraph_style(
            p,
            size=28,              # un poco más grande
            bold=True,
            color=Theme.PRIMARY,
            line_spacing=1.1,
            font_name=Theme.FONT_TITLE,
        )

    # PORTADA
    def _add_cover_slide(self, title, subtitle, total_responses):
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        
        # Fondo split
        bg_left = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(5.7), Inches(7.5))
        bg_left.fill.solid()
        bg_left.fill.fore_color.rgb = Theme.PRIMARY
        bg_left.line.fill.background()

        bg_right = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(5.7), 0, Inches(7.633), Inches(7.5))
        bg_right.fill.solid()
        bg_right.fill.fore_color.rgb = Theme.BG_SLIDE
        bg_right.line.fill.background()

        # Título principal
        tb_title = slide.shapes.add_textbox(Inches(0.8), Inches(2.1), Inches(4.5), Inches(2.4))
        tf = tb_title.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE

        p = tf.paragraphs[0]
        p.text = title[:70]
        self._set_paragraph_style(
            p,
            size=44,
            bold=True,
            color=Theme.TEXT_LIGHT,
            line_spacing=1.15,
            font_name=Theme.FONT_TITLE,
        )

        # Subtítulo (rango de fechas)
        if subtitle:
            p_sub = tf.add_paragraph()
            p_sub.text = subtitle
            self._set_paragraph_style(
                p_sub,
                size=18,
                bold=False,
                color=Theme.ACCENT,
                line_spacing=1.2,
                font_name=Theme.FONT_BODY,
            )

        # KPI Respuestas
        self._create_card(slide, Inches(6.3), Inches(2.7), Inches(5.3), Inches(2.4))
        
        tb_lbl = slide.shapes.add_textbox(Inches(6.3), Inches(2.8), Inches(5.3), Inches(0.55))
        p_l = tb_lbl.text_frame.paragraphs[0]
        p_l.text = "RESPUESTAS RECIBIDAS"
        self._set_paragraph_style(
            p_l,
            size=12,
            bold=True,
            color=Theme.TEXT_MUTED,
            align=PP_ALIGN.CENTER,
            font_name=Theme.FONT_BODY,
        )
        
        tb_kpi = slide.shapes.add_textbox(Inches(6.3), Inches(3.4), Inches(5.3), Inches(1.5))
        p_k = tb_kpi.text_frame.paragraphs[0]
        p_k.text = f"{total_responses:,}"
        self._set_paragraph_style(
            p_k,
            size=60,
            bold=True,
            color=Theme.PRIMARY,
            align=PP_ALIGN.CENTER,
            font_name=Theme.FONT_TITLE,
        )



    # NPS
    def _add_nps_slide(self, nps_data: dict):
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = Theme.BG_SLIDE
        self._add_header(slide, "Net Promoter Score (NPS)")

        self._create_card(slide, Inches(0.4), Inches(1.3), Inches(12.5), Inches(5.8))

        score = nps_data.get('score', 0)
        has_data = nps_data.get('promoters', 0) + nps_data.get('passives', 0) + nps_data.get('detractors', 0) > 0
        
        # Score principal
        tb_score = slide.shapes.add_textbox(Inches(0.8), Inches(1.7), Inches(3.4), Inches(2.1))
        tf = tb_score.text_frame
        tf.vertical_anchor = MSO_ANCHOR.TOP
        tf.word_wrap = True
        
        p_s = tf.paragraphs[0]
        if has_data:
            p_s.text = f"NPS: {score}"
            self._set_paragraph_style(
                p_s,
                size=46,
                bold=True,
                color=Theme.PRIMARY,
                font_name=Theme.FONT_TITLE,
            )
        else:
            p_s.text = "NPS: Sin datos"
            self._set_paragraph_style(
                p_s,
                size=34,
                bold=True,
                color=Theme.TEXT_MUTED,
                font_name=Theme.FONT_TITLE,
            )

        # Breakdown
        if has_data:
            p_break = tf.add_paragraph()
            p_break.text = f"\nPromotores: {nps_data.get('promoters', 0):,}"
            self._set_paragraph_style(
                p_break,
                size=15,
                bold=False,
                color=RGBColor(16, 185, 129),
                line_spacing=1.4,
            )

            p_pass = tf.add_paragraph()
            p_pass.text = f"Pasivos: {nps_data.get('passives', 0):,}"
            self._set_paragraph_style(
                p_pass,
                size=15,
                bold=False,
                color=RGBColor(100, 116, 139),
                line_spacing=1.2,
            )

            p_det = tf.add_paragraph()
            p_det.text = f"Detractores: {nps_data.get('detractors', 0):,}"
            self._set_paragraph_style(
                p_det,
                size=15,
                bold=False,
                color=RGBColor(239, 68, 68),
                line_spacing=1.2,
            )

        # Gráfica
        chart_b64 = nps_data.get('chart_image')
        if not chart_b64 and has_data:
            chart_b64 = ChartGenerator.generate_nps_chart(
                nps_data.get('promoters', 0),
                nps_data.get('passives', 0),
                nps_data.get('detractors', 0)
            )
        
        if chart_b64:
            img_stream = self._decode_image(chart_b64)
            if img_stream:
                try:
                    slide.shapes.add_picture(img_stream, Inches(4.7), Inches(1.6), width=Inches(7.9))
                except Exception as e:
                    logger.error(f"Error insertando gráfica NPS: {e}")

    # CONTENIDO (Preguntas)
    def _add_content_slide(self, item: dict):
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = Theme.BG_SLIDE

        q_text = self._clean_text(item.get('text', 'Pregunta'))
        self._add_header(slide, q_text)

        # Tarjetas
        self._create_card(slide, Inches(0.4), Inches(1.2), Inches(7.8), Inches(5.9))
        self._create_card(slide, Inches(8.4), Inches(1.2), Inches(4.5), Inches(5.9))

        # RENDERIZADO SEGÚN TIPO
        q_type = item.get("type", "").lower()
        options = item.get("options", [])
        chart_b64 = item.get("chart_image")
        
        logger.info(f"Slide: '{q_text[:40]}' | Tipo: {q_type} | Opciones: {len(options)}")

        if q_type in ["text", "abierta"]:
            samples = item.get("samples_texto", []) or item.get("text_samples", [])
            self._render_text_answers(slide, samples)
        
        elif q_type in ["number", "numeric", "edad", "rating"]:
            numeric_values = item.get("numeric_values", [])
            
            if not numeric_values and options:
                numeric_values = []
                for opt in options:
                    try:
                        val = float(str(opt.get('label', '')).replace(',', ''))
                        count = opt.get('count', 0)
                        numeric_values.extend([val] * count)
                    except ValueError:
                        pass
            
            if numeric_values and not chart_b64:
                chart_b64 = ChartGenerator.generate_numeric_distribution(numeric_values, q_text)
            
            if chart_b64:
                self._insert_chart(slide, chart_b64, Inches(0.7), Inches(1.5), Inches(7.2))
            else:
                self._render_stats_card(slide, item)
        
        else:
            # Opción múltiple
            if not chart_b64 and options:
                has_data = any(opt.get('count', 0) > 0 for opt in options)
                
                if has_data:
                    if len(options) <= 5:
                        chart_b64 = ChartGenerator.generate_pie_chart(options, q_text)
                    else:
                        chart_b64 = ChartGenerator.generate_bar_chart(options, q_text)
            
            if chart_b64:
                self._insert_chart(slide, chart_b64, Inches(0.7), Inches(1.5), Inches(7.2))
            elif options:
                self._render_native_table(slide, options, Inches(0.7), Inches(1.6), Inches(7.2))

        # INSIGHT con mejor legibilidad
        insight = self._clean_text(item.get("insight", "Sin análisis disponible."))
        tb_ins = slide.shapes.add_textbox(Inches(8.6), Inches(1.4), Inches(4.1), Inches(5.5))
        tf = tb_ins.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.TOP
        tf.margin_left = Inches(0.22)
        tf.margin_right = Inches(0.22)
        tf.margin_top = Inches(0.18)

        # Título del bloque
        p_head = tf.paragraphs[0]
        p_head.text = "ANÁLISIS INTELIGENTE"
        self._set_paragraph_style(
            p_head,
            size=16,
            bold=True,
            color=Theme.SECONDARY,
            line_spacing=1.1,
            font_name=Theme.FONT_TITLE,
        )
        p_head.space_after = Pt(10)

        # Magia: ajuste de fuente progresivo sin límite de texto
        font_size = 12

        # Colores diferenciados para bloques
        color_main = Theme.TEXT_MAIN
        color_num = RGBColor(16, 185, 129)  # verde para números
        color_alert = RGBColor(251, 191, 36)  # amarillo para notas
        color_black = RGBColor(15, 23, 42)  # negro para el resto

        # Dividir el insight en líneas/párrafos por saltos de línea reales
        insight_lines = insight.splitlines()
        import random
        NOTE_VARIANTS = {
            # Dispersión
            "Nota: Hay alta dispersión, ninguna opción supera el 35%.": [
                "Nota: Hay alta dispersión, ninguna opción supera el 35%.",
                "Nota: Las respuestas están muy repartidas, ninguna alternativa supera el 35%.",
                "Nota: Existe dispersión significativa, ninguna opción alcanza el 35%.",
                "Nota: No hay una opción dominante, todas están por debajo del 35%.",
                "Nota: Alta dispersión detectada, ninguna respuesta supera el 35%."
            ],
            # Pocas respuestas
            "Nota: El número de respuestas es bajo.": [
                "Nota: El número de respuestas es bajo.",
                "Nota: Hay poca participación en esta pregunta.",
                "Nota: Se recibieron pocas respuestas para este ítem.",
                "Nota: La muestra de respuestas es reducida.",
                "Nota: Respuestas insuficientes para un análisis robusto."
            ],
            # Sin respuestas
            "Nota: No se recibieron respuestas para esta pregunta.": [
                "Nota: No se recibieron respuestas para esta pregunta.",
                "Nota: Esta pregunta no obtuvo respuestas.",
                "Nota: Sin datos disponibles para esta pregunta.",
                "Nota: No hay información para analizar en este ítem.",
                "Nota: No se cuenta con respuestas para este caso."
            ],
            # Respuestas concentradas
            "Nota: Más del 80% eligió la misma opción.": [
                "Nota: Más del 80% eligió la misma opción.",
                "Nota: Existe alta concentración de respuestas en una sola opción.",
                "Nota: La mayoría absoluta seleccionó la misma alternativa.",
                "Nota: Respuestas muy concentradas en una opción (>80%).",
                "Nota: Predominio claro de una respuesta (>80%)."
            ],
            # Respuestas abiertas genéricas
            "Nota: Las respuestas abiertas son muy variadas.": [
                "Nota: Las respuestas abiertas son muy variadas.",
                "Nota: Gran diversidad en las respuestas abiertas.",
                "Nota: No hay tendencia clara en las respuestas abiertas.",
                "Nota: Las opiniones abiertas son dispersas.",
                "Nota: Respuestas abiertas sin patrón dominante."
            ]
        }
        # Lógica para variar la nota solo si se repite en slides consecutivos
        if not hasattr(self, '_last_slide_notes'):
            self._last_slide_notes = {}
        current_slide_notes = {}
        for line in insight_lines:
            l_str = line.strip()
            if not l_str:
                continue
            base_note = l_str
            variants = NOTE_VARIANTS.get(base_note)
            # Si la nota tiene variantes y se repite respecto al slide anterior, elegir una variante diferente
            if variants:
                last_variant = self._last_slide_notes.get(base_note)
                # Si la nota se repite exactamente igual que en el slide anterior, elegir una variante diferente
                if last_variant:
                    available = [v for v in variants if v != last_variant]
                    if available:
                        l_str = random.choice(available)
                    else:
                        l_str = last_variant
                else:
                    l_str = random.choice(variants)
                current_slide_notes[base_note] = l_str
            is_recommendation = l_str.startswith(('👀', '💡', '⚠', 'Recomendación', 'Nota'))
            p_body = tf.add_paragraph()
            p_body.text = l_str
            self._set_paragraph_style(
                p_body,
                size=font_size,
                bold=False,
                color=color_alert if is_recommendation else color_black,
                line_spacing=1.5,
                font_name=Theme.FONT_BODY,
            )
            p_body.alignment = PP_ALIGN.JUSTIFY
        self._last_slide_notes = current_slide_notes

    def _insert_chart(self, slide, chart_b64, x, y, w):
        """Helper para insertar gráficas con manejo de errores."""
        img_stream = self._decode_image(chart_b64)
        if img_stream:
            try:
                slide.shapes.add_picture(img_stream, x, y, width=w)
            except Exception as e:
                logger.error(f"Error insertando gráfica: {e}")

    def _render_stats_card(self, slide, item):
        """Tarjeta de estadísticas numéricas más legible."""
        stats = item.get('stats', {})
        
        y_pos = Inches(2.5)
        stats_list = [
            ("Promedio", stats.get('mean') or stats.get('promedio')),
            ("Mediana", stats.get('median') or stats.get('mediana')),
            ("Máximo", stats.get('max') or stats.get('maximo')),
            ("Mínimo", stats.get('min') or stats.get('minimo')),
        ]
        
        for label, value in stats_list:
            if value is None or value == 0:
                continue
            
            tb = slide.shapes.add_textbox(Inches(2), y_pos, Inches(5), Inches(0.6))
            p = tb.text_frame.paragraphs[0]
            p.text = f"{label}: {value:.2f}" if isinstance(value, float) else f"{label}: {value:,}"
            p.font.size = Pt(18)  # Aumentado de 16 a 18
            p.font.bold = True
            p.font.color.rgb = Theme.PRIMARY
            y_pos += Inches(0.75)

    def _render_native_table(self, slide, options, x, y, w):
        """Tabla limpia con textos más grandes."""
        if not options:
            return
        
        valid_options = [opt for opt in options if opt.get('count', 0) > 0]
        if not valid_options:
            valid_options = options[:8]
        else:
            valid_options = sorted(valid_options, key=lambda o: o.get('count', 0), reverse=True)[:8]
        
        rows = len(valid_options)
        cols = 3
        
        try:
            row_height = min(0.45, 3.2 / (rows + 1))  # Aumentado para más espacio
            table_shape = slide.shapes.add_table(rows+1, cols, x, y, w, Inches(row_height*(rows+1)))
            tbl = table_shape.table
            
            headers = ["Opción", "Cant", "%"]
            widths = [0.55, 0.23, 0.22]
            
            # Header con mejor formato
            for i, h in enumerate(headers):
                cell = tbl.cell(0, i)
                cell.text = h
                cell.fill.solid()
                cell.fill.fore_color.rgb = Theme.PRIMARY
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                
                p = cell.text_frame.paragraphs[0]
                p.font.color.rgb = Theme.TEXT_LIGHT
                p.font.bold = True
                p.font.size = Pt(12)
                p.alignment = PP_ALIGN.CENTER
                
                tbl.columns[i].width = int(w.inches * widths[i] * 914400)
                
            # Data con mejor legibilidad
            total_counts = sum(opt.get('count', 0) for opt in valid_options)
            for i, opt in enumerate(valid_options):
                r = i + 1
                
                # Opción
                cell_opt = tbl.cell(r, 0)
                cell_opt.text = str(opt.get('label', '-'))[:40]
                cell_opt.vertical_anchor = MSO_ANCHOR.MIDDLE
                cell_opt.text_frame.paragraphs[0].font.size = Pt(11)
                cell_opt.text_frame.paragraphs[0].font.color.rgb = Theme.TEXT_MAIN
                cell_opt.text_frame.margin_left = Inches(0.08)
                cell_opt.text_frame.margin_right = Inches(0.08)
                
                # Cantidad
                cell_cnt = tbl.cell(r, 1)
                cell_cnt.text = f"{opt.get('count', 0):,}"
                cell_cnt.vertical_anchor = MSO_ANCHOR.MIDDLE
                cell_cnt.text_frame.paragraphs[0].font.size = Pt(11)
                cell_cnt.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
                cell_cnt.text_frame.paragraphs[0].font.color.rgb = Theme.TEXT_MAIN
                cell_cnt.text_frame.paragraphs[0].font.bold = True
                
                # Porcentaje
                pct = opt.get('percent', 0)
                if pct == 0 and total_counts > 0:
                    pct = round((opt.get('count', 0) / total_counts * 100), 1)
                
                cell_pct = tbl.cell(r, 2)
                cell_pct.text = f"{pct}%"
                cell_pct.vertical_anchor = MSO_ANCHOR.MIDDLE
                cell_pct.text_frame.paragraphs[0].font.size = Pt(11)
                cell_pct.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
                cell_pct.text_frame.paragraphs[0].font.color.rgb = Theme.TEXT_MAIN
                cell_pct.text_frame.paragraphs[0].font.bold = True
                
                # Alternar color en filas
                if r % 2 == 0:
                    for c in range(3):
                        tbl.cell(r, c).fill.solid()
                        tbl.cell(r, c).fill.fore_color.rgb = RGBColor(248, 250, 252)
        except Exception as e:
            logger.error(f"Error creando tabla: {e}", exc_info=True)