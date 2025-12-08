"""
Utilidades para generación de gráficos con Matplotlib y Seaborn.
Centraliza toda la lógica de visualización de datos.
Optimizado para entornos sin interfaz gráfica (Agg backend).
"""
import io
import base64
import logging
import matplotlib
# Configurar backend no interactivo antes de importar pyplot
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

logger = logging.getLogger(__name__)

class ChartGenerator:
    """Generador centralizado de gráficos para análisis de encuestas."""
    
    # Configuración de estilo común
    STYLE_CONFIG = {
        'font.family': 'sans-serif',
        'font.sans-serif': ['Arial', 'DejaVu Sans', 'Liberation Sans', 'sans-serif'],
        'font.size': 9,
        'axes.unicode_minus': False  # Evita problemas con signos negativos en algunas fuentes
    }
    
    # Paleta corporativa
    COLORS = {
        'primary': '#0d6efd',
        'success': '#10b981',
        'warning': '#fbbf24',
        'danger': '#ef4444',
        'dark': '#111827',
        'text': '#374151',
        'grid': '#e5e7eb'
    }

    @classmethod
    def _setup_figure(cls, figsize=(7, 4), dark_mode=False):
        """Configura y retorna una nueva figura limpia, con soporte para modo oscuro."""
        plt.style.use('default')
        plt.rcParams.update(cls.STYLE_CONFIG)
        bg = '#1f2937' if dark_mode else 'white'
        fig, ax = plt.subplots(figsize=figsize, facecolor=bg)
        ax.set_facecolor(bg)
        return fig, ax

    @staticmethod
    def _fig_to_base64(fig, dpi=150):
        """Convierte una figura de matplotlib a base64 y limpia memoria."""
        try:
            buf = io.BytesIO()
            plt.savefig(buf, format="png", dpi=dpi, bbox_inches='tight', transparent=True)
            plt.close(fig) # CRÍTICO: Liberar memoria
            buf.seek(0)
            return base64.b64encode(buf.read()).decode("utf-8")
        except Exception as e:
            logger.error(f"Error convirtiendo gráfico a base64: {e}")
            plt.close(fig)
            return None

    @classmethod
    def generate_heatmap(cls, df, dark_mode=False):
        """Genera un mapa de calor de correlaciones."""
        if df is None or df.empty: return None

        # 1. Limpieza y Selección de Datos Numéricos
        try:
            df_numeric = df.select_dtypes(include=['number'])
            # Intentar coerción si no hay numéricos detectados
            if df_numeric.empty:
                df_numeric = df.apply(pd.to_numeric, errors='coerce').dropna(axis=1, how='all')
            
            # Filtro de dimensiones mínimas
            if df_numeric.shape[1] < 2 or df_numeric.shape[0] < 2: return None
            
            # Matriz de correlación
            corr_matrix = df_numeric.corr().dropna(how='all', axis=0).dropna(how='all', axis=1)
            if corr_matrix.empty or corr_matrix.shape[0] < 2: return None
        except Exception as e:
            logger.warning(f"Error procesando datos para heatmap: {e}")
            return None

        # 2. Configuración Visual
        n_questions = corr_matrix.shape[0]
        # Tamaño dinámico inteligente
        fig_width = max(8, min(14, n_questions * 1.2))
        fig_height = max(6, min(12, n_questions * 0.8))
        
        theme = {
            'bg': '#1f2937' if dark_mode else 'white',
            'text': '#e5e7eb' if dark_mode else '#374151',
            'line': '#374151' if dark_mode else 'white'
        }

        fig, ax = plt.subplots(figsize=(fig_width, fig_height), facecolor=theme['bg'])
        ax.set_facecolor(theme['bg'])

        # 3. Etiquetas Truncadas
        short_labels = [cls._truncate_label(col) for col in corr_matrix.columns]
        corr_matrix.columns = short_labels
        corr_matrix.index = short_labels

        # 4. Renderizado
        try:
            sns.heatmap(
                corr_matrix,
                annot=True,
                cmap='RdYlGn',
                fmt=".2f",
                linewidths=1,
                linecolor=theme['line'],
                vmin=-1, vmax=1,
                ax=ax,
                cbar_kws={'shrink': 0.8},
                square=True,
                annot_kws={'size': 9}
            )
            
            ax.set_title('Mapa de Correlaciones', fontsize=12, weight='bold', pad=15, color=theme['text'])
            
            # Ajuste de ejes
            plt.xticks(rotation=45, ha='right', fontsize=9, color=theme['text'])
            plt.yticks(rotation=0, fontsize=9, color=theme['text'])
            
            # Ajuste colorbar
            if ax.collections:
                cbar = ax.collections[0].colorbar
                cbar.ax.yaxis.set_tick_params(color=theme['text'])
                plt.setp(plt.getp(cbar.ax.axes, 'yticklabels'), color=theme['text'])

            return cls._fig_to_base64(fig, dpi=120)
        except Exception as e:
            logger.error(f"Error renderizando heatmap: {e}")
            plt.close(fig)
            return None

    @staticmethod
    def _truncate_label(text, max_length=25):
        text = str(text)
        prefixes = ['¿Qué tan ', '¿Cómo ', '¿Cuál ', '¿Por qué ', '¿Dónde ', '¿Cuándo ', 'Please rate']
        for p in prefixes:
            if text.startswith(p): text = text[len(p):]
        return (text[:max_length] + '..') if len(text) > max_length else text

    @classmethod
    def generate_donut_chart(cls, labels, counts, title=None, colors=None, dark_mode=False):
        """Generador genérico de gráficos de dona (usado por Pie y NPS), ahora con soporte para modo oscuro."""
        # Filtrar vacíos
        valid_data = [(l, c) for l, c in zip(labels, counts) if c > 0]
        if not valid_data: return None
        
        f_labels, f_counts = zip(*valid_data)
        
        fig, ax = cls._setup_figure(figsize=(5, 5), dark_mode=dark_mode)
        
        if not colors:
            palette = sns.color_palette('tab10' if len(f_labels) <= 10 else 'hls', n_colors=len(f_labels))
            colors = [tuple(x for x in p) for p in palette]

        text_color = '#e5e7eb' if dark_mode else '#333333'
        wedges, texts, autotexts = ax.pie(
            f_counts,
            labels=f_labels,
            autopct='%1.0f%%',
            startangle=90,
            colors=colors,
            pctdistance=0.85,
            textprops=dict(color=text_color, fontsize=9, weight='bold')
        )
        
        # Círculo central
        centre_circle = plt.Circle((0, 0), 0.60, fc='#1f2937' if dark_mode else 'white')
        fig.gca().add_artist(centre_circle)
        ax.axis('equal')
        
        if title:
            ax.set_title(title, fontsize=11, weight='bold', color=text_color, pad=10)
            
        return cls._fig_to_base64(fig)

    @classmethod
    def generate_nps_chart(cls, promotores, pasivos, detractores):
        return cls.generate_donut_chart(
            ['Promotores', 'Pasivos', 'Detractores'],
            [promotores, pasivos, detractores],
            colors=[cls.COLORS['success'], cls.COLORS['warning'], cls.COLORS['danger']]
        )

    @classmethod
    def generate_pie_chart(cls, labels, counts, title, dark_mode=False):
        return cls.generate_donut_chart(labels, counts, title, dark_mode=dark_mode)

    @classmethod
    def generate_vertical_bar_chart(cls, labels, counts, title, dark_mode=False):
        fig, ax = cls._setup_figure(dark_mode=dark_mode)
        # Truncar etiquetas largas en eje X
        short_labels = [cls._truncate_label(l, 15) for l in labels]
        bar_color = '#60a5fa' if dark_mode else cls.COLORS['primary']
        bars = ax.bar(short_labels, counts, color=bar_color, alpha=0.9, width=0.6)
        text_color = '#e5e7eb' if dark_mode else cls.COLORS['dark']
        grid_color = '#374151' if dark_mode else cls.COLORS['grid']
        ax.set_title(title, fontsize=12, weight='bold', color=text_color, pad=15)
        # Limpieza visual
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.spines['bottom'].set_color(grid_color)
        ax.tick_params(axis='y', left=False, labelleft=False)
        ax.bar_label(bars, fmt='%d', padding=3, fontsize=10, weight='bold', color=text_color)
        plt.tight_layout()
        return cls._fig_to_base64(fig)

    @classmethod
    def generate_horizontal_bar_chart(cls, labels, counts, title, dark_mode=False):
        height = max(3, len(labels) * 0.5)
        fig, ax = cls._setup_figure(figsize=(7, height), dark_mode=dark_mode)
        y_pos = range(len(labels))
        bar_color = '#60a5fa' if dark_mode else cls.COLORS['primary']
        bars = ax.barh(y_pos, counts, color=bar_color, alpha=0.9, height=0.6)
        short_labels = [cls._truncate_label(l, 35) for l in labels]
        text_color = '#e5e7eb' if dark_mode else cls.COLORS['text']
        grid_color = '#374151' if dark_mode else cls.COLORS['grid']
        ax.set_yticks(y_pos)
        ax.set_yticklabels(short_labels, fontsize=10, color=text_color)
        ax.invert_yaxis()
        ax.set_title(title, fontsize=12, weight='bold', color=text_color, pad=15)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.tick_params(axis='x', bottom=False, labelbottom=False)
        ax.bar_label(bars, fmt='%d', padding=5, fontsize=10, weight='bold', color=text_color)
        plt.tight_layout()
        return cls._fig_to_base64(fig)