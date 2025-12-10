"""
Utilidades para generación de gráficos con Matplotlib y Seaborn.
Centraliza toda la lógica de visualización de datos.
Optimizado para entornos sin interfaz gráfica (Agg backend).
"""
import io
import base64
import logging
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import itertools

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

    # 🔧 Corregido: agregamos success / warning / danger usados por generate_nps_chart
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

    BASE_STYLE = {
        'font.family': 'sans-serif',
        'font.sans-serif': ['Inter', 'system-ui', 'Segoe UI', 'sans-serif'],
        'font.size': 11,
        'axes.unicode_minus': False,
        'axes.linewidth': 0,
    }

    @classmethod
    def _apply_style(cls, dark_mode=False):
        theme = cls.THEME_COLORS['dark'] if dark_mode else cls.THEME_COLORS['light']
        plt.style.use('default')
        params = {
            **cls.BASE_STYLE,
            'text.color': theme['text'],
            'axes.labelcolor': theme['text'],
            'xtick.color': theme['text'],
            'ytick.color': theme['text'],
            'axes.facecolor': 'none',
            'figure.facecolor': 'none',
            'savefig.facecolor': 'none',
            'savefig.transparent': True,
            'axes.edgecolor': 'none',
            'grid.color': theme['grid'],
            'grid.linestyle': ':',
            'grid.linewidth': 1.0,
            'grid.alpha': 0.4,
        }
        plt.rcParams.update(params)
        sns.set_style(
            "whitegrid",
            {
                "axes.facecolor": "none",
                "figure.facecolor": "none",
                "grid.color": theme['grid'],
                "text.color": theme['text'],
                "axes.labelcolor": theme['text'],
                "xtick.color": theme['text'],
                "ytick.color": theme['text'],
            },
        )
        return theme

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

    @staticmethod
    def _fig_to_base64(fig, dpi=130):
        try:
            buf = io.BytesIO()
            plt.savefig(
                buf,
                format="png",
                dpi=dpi,
                bbox_inches='tight',
                pad_inches=0.1,
                transparent=True,
            )
            plt.close(fig)
            buf.seek(0)
            return base64.b64encode(buf.read()).decode("utf-8")
        except Exception as e:
            logger.error(f"Error chart: {e}")
            plt.close(fig)
            return None

    @classmethod
    def _optimize_data_visuals(cls, labels, counts, limit=15):
        """
        Agrupa el exceso de datos en 'Otros' para evitar saturación visual.
        Ordena de mayor a menor.
        """
        if not labels or not counts:
            return [], []

        # Unir y ordenar
        data = sorted(zip(labels, counts), key=lambda x: x[1], reverse=True)

        if len(data) <= limit:
            # Devuelve (labels, counts)
            if not data:
                return [], []
            l, c = zip(*data)
            return list(l), list(c)

        # Tomar Top (limit - 1)
        top_data = data[: limit - 1]
        other_data = data[limit - 1 :]

        # Calcular suma de otros
        other_count = sum(item[1] for item in other_data)

        # Reconstruir
        final_labels = [item[0] for item in top_data] + ['Otros (Resto)']
        final_counts = [item[1] for item in top_data] + [other_count]

        return final_labels, final_counts

    # ==========================
    # TIPOS DE GRÁFICOS
    # ==========================

    @classmethod
    def generate_heatmap(cls, df, dark_mode=False):
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
            # Limitar correlación a 20x20 máximo para que no explote
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
        fig_width = max(8, min(14, n_cols * 1.1))
        fig_height = max(6, min(12, n_cols * 0.8))

        fig, ax, theme = cls._setup_figure(
            figsize=(fig_width, fig_height), dark_mode=dark_mode
        )

        labels = [
            str(c)[:18] + '..' if len(str(c)) > 18 else str(c)
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
                linewidths=2,
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
                pad=20,
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
        # Optimización: Agrupar en Otros si hay > 12 rebanadas
        f_labels, f_counts = cls._optimize_data_visuals(labels, counts, limit=12)
        if not f_labels:
            return None

        fig, ax, theme = cls._setup_figure(
            figsize=(6, 4.5), dark_mode=dark_mode
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
            (0, 0), 0.50, fc='none', linewidth=0
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
                pad=15,
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
        # Optimización: Top 20 para barras estáticas
        f_labels, f_counts = cls._optimize_data_visuals(labels, counts, limit=20)

        height = max(4, len(f_labels) * 0.7)
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
            height=0.75,
            zorder=3,
        )

        short_labels = [str(l)[:40] for l in f_labels]

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
            fontsize=13,
            weight='bold',
            pad=20,
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
            padding=8,
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
        # Optimización: Top 15 para vertical (más limitado por el ancho)
        f_labels, f_counts = cls._optimize_data_visuals(labels, counts, limit=15)

        fig, ax, theme = cls._setup_figure(dark_mode=dark_mode)

        short_labels = [str(l)[:15] for l in f_labels]
        bar_colors = cls._get_colors(len(f_labels))

        bars = ax.bar(
            short_labels,
            f_counts,
            color=bar_colors,
            alpha=0.95,
            width=0.75,
            zorder=3,
        )

        ax.set_title(
            title,
            fontsize=13,
            weight='bold',
            pad=20,
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
        )  # Rotación para evitar overlap
        ax.tick_params(axis='y', left=False, labelleft=False)

        ax.bar_label(
            bars,
            fmt='%d',
            padding=4,
            fontsize=11,
            weight='bold',
            color=theme['text'],
        )

        plt.tight_layout()
        return cls._fig_to_base64(fig)

    # 🔥 Nuevo alias usado por survey_analysis.py
    @classmethod
    def generate_bar_chart(cls, labels, counts, title, dark_mode=False):
        """
        Alias retrocompatible que delega en generate_vertical_bar_chart.
        Lo usamos desde el motor de análisis para desacoplar el tipo de barra.
        """
        return cls.generate_vertical_bar_chart(
            labels, counts, title, dark_mode=dark_mode
        )
