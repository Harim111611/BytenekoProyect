"""
Utilidades para generación de gráficos con Matplotlib y Seaborn.
Centraliza toda la lógica de visualización de datos.
Optimizado para entornos sin interfaz gráfica (Agg backend).
"""
import io
import base64
import logging

# --- Plotly para gráficos interactivos ---
import plotly.graph_objects as go
import plotly.io as pio
import pandas as pd
import itertools
import matplotlib.pyplot as plt # Asegurar importacion de pyplot
import seaborn as sns # Asegurar importacion de seaborn

logger = logging.getLogger(__name__)


class ChartGenerator:
    """
    Generador centralizado de gráficos.
    ESTILO: Organic Integration + Data Optimization (Manejo de grandes volúmenes).
    """

    FRIENDLY_PALETTE = [
        '#6366f1', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#06b6d4',
        '#f43f5e', '#84cc16', '#3b82f6', '#f97316', '#14b8a6', '#d946ef',
        '#64748b', '#ef4444', '#22c55e', '#eab308', '#a855f7', '#0ea5e9',
        '#f472b6', '#a3e635'
    ]

    THEME_COLORS = {
        'light': {
            'text': '#374151',
            'grid': '#9ca3af',
            'primary': '#6366f1',
            'edge_contrast': '#ffffff',
            'success': '#16a34a',
            'warning': '#f59e0b',
            'danger': '#dc2626',
        },
        'dark': {
            'text': '#f3f4f6',
            'grid': '#4b5563',
            'primary': '#818cf8',
            'edge_contrast': '#161b22',
            'success': '#22c55e',
            'warning': '#facc15',
            'danger': '#f97316',
        }
    }

    # AJUSTE 1: Fuentes más grandes por defecto para mejor lectura
    BASE_STYLE = {
        'font.family': 'sans-serif',
        'font.sans-serif': ['Inter', 'system-ui', 'Segoe UI', 'sans-serif'],
        'font.size': 12,           # Aumentado de 11 a 12
        'axes.labelsize': 12,      # Etiquetas ejes
        'axes.titlesize': 14,      # Títulos más grandes
        'xtick.labelsize': 11,
        'ytick.labelsize': 11,
        'axes.unicode_minus': False,
        'axes.linewidth': 0,
    }

    @classmethod
    def _apply_style(cls, dark_mode=False):
         # Helper simple para aplicar estilos a matplotlib
        theme = cls._get_theme(dark_mode)
        plt.rcParams.update(cls.BASE_STYLE)
        plt.rcParams['text.color'] = theme['text']
        plt.rcParams['axes.labelcolor'] = theme['text']
        plt.rcParams['xtick.color'] = theme['text']
        plt.rcParams['ytick.color'] = theme['text']
        return theme

    @classmethod
    def _get_theme(cls, dark_mode=False):
        return cls.THEME_COLORS['dark'] if dark_mode else cls.THEME_COLORS['light']

    @classmethod
    def _setup_figure(cls, figsize=(7, 4), dark_mode=False):
        theme = cls._apply_style(dark_mode)
        fig, ax = plt.subplots(figsize=figsize, facecolor='none')
        ax.set_facecolor('none')
        return fig, ax, theme

    @staticmethod
    def _get_colors(n_colors):
        return [
            c
            for i, c in zip(
                range(n_colors),
                itertools.cycle(ChartGenerator.FRIENDLY_PALETTE),
            )
        ]
    
    @classmethod
    def _fig_to_base64(cls, fig):
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', transparent=True)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode('utf-8')

    @staticmethod
    def _fig_to_html(fig):
        try:
            return pio.to_html(fig, full_html=False, include_plotlyjs='cdn', config={
                'displayModeBar': False,
                'responsive': True # IMPORTANTE: Permite que el JS ajuste el ancho
            })
        except Exception as e:
            logger.error(f"Error chart (plotly): {e}")
            return None

    @classmethod
    def generate_horizontal_bar_chart_plotly(
        cls, labels, counts, title=None, dark_mode=False, hover_data=None
    ):
        import plotly.express as px
        theme = cls._get_theme(dark_mode)
        import pandas as pd
        df = pd.DataFrame({
            'label': labels,
            'count': counts,
        })
        if hover_data:
            for k, v in hover_data.items():
                df[k] = v
        
        # --- CÁLCULO DE MÁRGENES DINÁMICOS ---
        
        # 1. Margen Izquierdo (Para las etiquetas de categoría ej: "Satisfacción...")
        max_label_len = max([len(str(l)) for l in labels]) if labels else 0
        left_margin = min(40 + max_label_len * 6.5, 220)  # Límite un poco más holgado pero controlado
        
        # 2. Margen Derecho (CRÍTICO: Para los números al final de la barra ej: "1512")
        max_count_len = max([len(str(c)) for c in counts]) if counts else 0
        # Base 20px + 9px por dígito aprox.
        right_margin = 25 + (max_count_len * 9) 

        # NOTA: Eliminamos 'width=fig_width' para que Plotly use el 100% del contenedor HTML
        
        fig = px.bar(
            df,
            x='count',
            y='label',
            orientation='h',
            color='count',
            color_continuous_scale=[
                'rgba(99,102,241,0.85)', 'rgba(16,185,129,0.85)', 'rgba(236,72,153,0.85)',
                'rgba(251,191,36,0.85)', 'rgba(139,92,246,0.85)', 'rgba(34,197,94,0.85)',
                'rgba(59,130,246,0.85)', 'rgba(244,63,94,0.85)', 'rgba(132,204,22,0.85)',
                'rgba(20,184,166,0.85)', 'rgba(168,85,247,0.85)', 'rgba(14,165,233,0.85)'
            ],
            labels={'count': 'Cantidad', 'label': 'Categoría'},
            height=320,
            # width se omite intencionalmente para responsividad
        )
        fig.update_traces(
            text=df['count'],
            textposition='outside', # Esto pone el número a la derecha
            marker_line_color=None,
            marker_line_width=0,
            hoverlabel=dict(bgcolor='rgba(99,102,241,0.15)', font_size=14, font_family='Inter, Segoe UI, Arial', font_color=theme['text']),
            marker=dict(line=dict(width=0),
                        color=df['count'],
                        coloraxis='coloraxis',
                        opacity=1,
                        ),
            width=0.7,
            customdata=df['count'],
            cliponaxis=False # Permite que el texto sobresalga un poco si es necesario (pero el margen lo controlará mejor)
        )
        fig.update_layout(
            title=title or '',
            autosize=True, # CRÍTICO: Permite ajustar al contenedor
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color=theme['text'], family='Inter, Segoe UI, Arial'),
            xaxis=dict(
                showgrid=True, 
                gridcolor='rgba(99,102,241,0.10)', 
                zeroline=False, 
                showline=False, 
                ticks='', 
                color=theme['text'],
                autorange=True,
            ),
            yaxis=dict(
                showgrid=False, 
                zeroline=False, 
                showline=False, 
                ticks='', 
                color=theme['text'],
                autorange="reversed" # A veces Plotly invierte el orden, aseguramos consistencia
            ),
            # Márgenes dinámicos aplicados aquí
            margin=dict(l=left_margin, r=right_margin, t=30, b=20),
            height=320,
            coloraxis_showscale=False,
            barcornerradius=4,
        )
        return cls._fig_to_html(fig)

    @classmethod
    def generate_doughnut_chart_plotly(
        cls, labels, counts, title=None, dark_mode=False
    ):
        theme = cls._get_theme(dark_mode)
        colors = [
            'rgba(99,102,241,0.85)', 'rgba(16,185,129,0.85)', 'rgba(236,72,153,0.85)',
            'rgba(251,191,36,0.85)', 'rgba(139,92,246,0.85)', 'rgba(34,197,94,0.85)',
            'rgba(59,130,246,0.85)', 'rgba(244,63,94,0.85)', 'rgba(132,204,22,0.85)',
            'rgba(20,184,166,0.85)', 'rgba(168,85,247,0.85)', 'rgba(14,165,233,0.85)'
        ][:len(labels)]
        fig = go.Figure(
            go.Pie(
                labels=labels,
                values=counts,
                hole=0.3,
                marker=dict(colors=colors, line=dict(color='rgba(255,255,255,0.7)', width=2)),
                textinfo='percent+label',
                hoverinfo='label+percent+value',
                textfont=dict(size=14, color=theme['text'], family='Inter, Segoe UI, Arial'),
            )
        )
        fig.update_traces(
            hoverlabel=dict(bgcolor='rgba(99,102,241,0.15)', font_size=14, font_family='Inter, Segoe UI, Arial', font_color=theme['text']),
            textfont_color=theme['text'],
            marker_line_color='rgba(255,255,255,0.7)',
        )
        fig.update_layout(
            title=title or '',
            showlegend=True,
            legend=dict(
                font=dict(color=theme['text'], size=12, family='Inter, Segoe UI, Arial'),
                orientation="h", # Leyenda horizontal para ahorrar espacio vertical
                yanchor="bottom",
                y=-0.2,
                xanchor="center",
                x=0.5
            ),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color=theme['text'], family='Inter, Segoe UI, Arial'),
            margin=dict(l=20, r=20, t=30, b=50), # Más margen abajo para la leyenda
            height=320,
            autosize=True,
        )
        return cls._fig_to_html(fig)

    @classmethod
    def _optimize_data_visuals(cls, labels, counts, limit=15):
        if not labels or not counts:
            return [], []

        data = sorted(zip(labels, counts), key=lambda x: x[1], reverse=True)

        if len(data) <= limit:
            if not data:
                return [], []
            l, c = zip(*data)
            return list(l), list(c)

        top_data = data[: limit - 1]
        other_data = data[limit - 1 :]
        other_count = sum(item[1] for item in other_data)

        final_labels = [item[0] for item in top_data] + ['Otros (Resto)']
        final_counts = [item[1] for item in top_data] + [other_count]

        return final_labels, final_counts

    # ==========================
    # TIPOS DE GRÁFICOS MATPLOTLIB (Mantenidos igual, solo optimizando espacios)
    # ==========================

    @classmethod
    def generate_heatmap(cls, df, dark_mode=False):
        # ... (Mantener código original, asegúrate de importar sns y plt arriba) ...
        # Por brevedad asumo que este código no cambia mucho, 
        # pero asegúrate de que fig_width no sea excesivo.
        if df is None or df.empty:
            return None
        try:
            df_numeric = df.select_dtypes(include=['number'])
            if df_numeric.empty:
                df_numeric = df.apply(
                    pd.to_numeric, errors='coerce'
                ).dropna(axis=1, how='all')
            if df_numeric.shape[1] < 2:
                return None
            if df_numeric.shape[1] > 20:
                df_numeric = df_numeric.iloc[:, :20]
            corr_matrix = (
                df_numeric.corr()
                .dropna(how='all', axis=0)
                .dropna(how='all', axis=1)
            )
            if corr_matrix.empty:
                return None
        except Exception:
            return None

        n_cols = corr_matrix.shape[1]
        # Ajustamos tamaños para que no sean gigantes
        fig_width = max(6, min(10, n_cols * 0.8))
        fig_height = max(5, min(9, n_cols * 0.6))

        fig, ax, theme = cls._setup_figure(
            figsize=(fig_width, fig_height), dark_mode=dark_mode
        )

        labels = [
            str(c)[:15] + '.' if len(str(c)) > 15 else str(c)
            for c in corr_matrix.columns
        ]
        corr_matrix.columns = labels
        corr_matrix.index = labels

        cmap = sns.diverging_palette(
            240, 10, s=90, l=55, n=20, as_cmap=True
        )

        try:
            heatmap = sns.heatmap(
                corr_matrix,
                annot=True,
                cmap=cmap,
                fmt=".2f",
                linewidths=1,
                linecolor=theme['edge_contrast'],
                vmin=-1,
                vmax=1,
                ax=ax,
                cbar_kws={'shrink': 0.8, 'aspect': 20, 'pad': 0.02},
                square=True,
                annot_kws={'size': 9, 'weight': 'bold'},
            )
            ax.set_title(
                'Mapa de Correlaciones',
                fontsize=13,
                weight='bold',
                pad=15,
                color=theme['text'],
            )
            plt.xticks(
                rotation=45,
                ha='right',
                fontsize=9,
                color=theme['text'],
            )
            plt.yticks(
                rotation=0,
                fontsize=9,
                color=theme['text'],
            )

            cbar = heatmap.collections[0].colorbar
            cbar.outline.set_visible(False)
            cbar.ax.yaxis.set_tick_params(color=theme['text'])
            plt.setp(
                plt.getp(cbar.ax.axes, 'yticklabels'),
                color=theme['text'],
            )

            return cls._fig_to_base64(fig)
        except Exception as e:
            logger.error(f"Heatmap error: {e}")
            plt.close(fig)
            return None

    @classmethod
    def generate_donut_chart(
        cls, labels, counts, title=None, colors=None, dark_mode=False
    ):
        f_labels, f_counts = cls._optimize_data_visuals(labels, counts, limit=12)
        if not f_labels:
            return None

        fig, ax, theme = cls._setup_figure(
            figsize=(6, 5), dark_mode=dark_mode
        )

        if not colors:
            colors = cls._get_colors(len(f_labels))

        wedges, texts, autotexts = ax.pie(
            f_counts,
            labels=None,
            autopct='%1.0f%%',
            startangle=90,
            colors=colors,
            pctdistance=0.78,
            wedgeprops={'linewidth': 0},
            textprops=dict(
                color='#ffffff', fontsize=10, weight='bold'
            ),
        )

        centre_circle = plt.Circle(
            (0, 0), 0.55, fc='none', linewidth=0
        )
        fig.gca().add_artist(centre_circle)

        ax.legend(
            wedges,
            f_labels,
            title="Opciones",
            loc="center left",
            bbox_to_anchor=(1, 0, 0.5, 1),
            frameon=False,
            fontsize=10,
        )

        if title:
            ax.set_title(
                title,
                fontsize=13,
                weight='bold',
                pad=10,
                color=theme['text'],
            )
        return cls._fig_to_base64(fig)

    @classmethod
    def generate_nps_chart(
        cls, promotores, pasivos, detractores, dark_mode=False
    ):
        theme = (
            cls.THEME_COLORS['dark']
            if dark_mode
            else cls.THEME_COLORS['light']
        )
        return cls.generate_donut_chart(
            ['Promotores', 'Pasivos', 'Detractores'],
            [promotores, pasivos, detractores],
            colors=[
                theme['success'],
                theme['warning'],
                theme['danger'],
            ],
            dark_mode=dark_mode,
        )

    @classmethod
    def generate_pie_chart(cls, labels, counts, title, dark_mode=False):
        return cls.generate_donut_chart(
            labels, counts, title, dark_mode=dark_mode
        )

    @classmethod
    def generate_horizontal_bar_chart(
        cls, labels, counts, title, dark_mode=False
    ):
        f_labels, f_counts = cls._optimize_data_visuals(labels, counts, limit=20)
        
        # Ajuste: Altura basada en items, pero ancho fijo razonable para imagen estática
        height = max(5, len(f_labels) * 0.6)
        
        fig, ax, theme = cls._setup_figure(
            figsize=(8, height), dark_mode=dark_mode
        )

        y_pos = range(len(f_labels))
        bar_colors = cls._get_colors(len(f_labels))

        bars = ax.barh(
            y_pos,
            f_counts,
            color=bar_colors,
            alpha=0.95,
            height=0.7,
            zorder=3,
        )

        short_labels = [str(l)[:35] for l in f_labels]

        ax.set_yticks(y_pos)
        ax.set_yticklabels(
            short_labels,
            fontsize=11,
            weight='medium',
            color=theme['text'],
        )
        ax.invert_yaxis()

        ax.set_title(
            title,
            fontsize=14,
            weight='bold',
            pad=15,
            color=theme['text'],
        )

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.tick_params(axis='x', bottom=False, labelbottom=False)
        ax.tick_params(axis='y', left=False)

        ax.bar_label(
            bars,
            fmt='%d',
            padding=5,
            fontsize=11,
            weight='bold',
            color=theme['text'],
        )

        plt.tight_layout()
        return cls._fig_to_base64(fig)

    @classmethod
    def generate_vertical_bar_chart(
        cls, labels, counts, title, dark_mode=False
    ):
        f_labels, f_counts = cls._optimize_data_visuals(labels, counts, limit=15)

        # Ancho contenido
        fig_width = max(7, len(f_labels) * 0.8)
        
        fig, ax, theme = cls._setup_figure(figsize=(fig_width, 5.5), dark_mode=dark_mode)

        short_labels = [str(l)[:12] for l in f_labels]
        bar_colors = cls._get_colors(len(f_labels))

        bars = ax.bar(
            short_labels,
            f_counts,
            color=bar_colors,
            alpha=0.95,
            width=0.6,
            zorder=3,
        )

        ax.set_title(
            title,
            fontsize=14,
            weight='bold',
            pad=15,
            color=theme['text'],
        )

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.spines['bottom'].set_color(theme['grid'])

        ax.grid(
            axis='y',
            linestyle='--',
            alpha=0.4,
            color=theme['grid'],
            zorder=0,
        )
        ax.tick_params(
            axis='x',
            colors=theme['text'],
            length=0,
            labelsize=10,
            rotation=30,
        )
        ax.tick_params(axis='y', left=False, labelleft=False)

        ax.bar_label(
            bars,
            fmt='%d',
            padding=3,
            fontsize=10,
            weight='bold',
            color=theme['text'],
        )

        plt.tight_layout()
        return cls._fig_to_base64(fig)

    @classmethod
    def generate_bar_chart(cls, labels, counts, title, dark_mode=False):
        return cls.generate_vertical_bar_chart(
            labels, counts, title, dark_mode=dark_mode
        )