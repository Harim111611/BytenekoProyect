"""
Utilidades para generación de gráficos con Matplotlib y Seaborn.
Centraliza toda la lógica de visualización de datos.
"""
import io
import base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd


class ChartGenerator:
    """Generador centralizado de gráficos para análisis de encuestas."""
    
    # Configuración de estilo común
    STYLE_CONFIG = {
        'font.family': 'sans-serif',
        'font.sans-serif': ['Arial'],
        'font.size': 9
    }
    
    @staticmethod
    def _configure_pyplot():
        """Aplica configuración común a todos los gráficos."""
        plt.style.use('default')
        plt.rcParams.update(ChartGenerator.STYLE_CONFIG)
    
    @staticmethod
    def _fig_to_base64(fig, dpi=150):
        """Convierte una figura de matplotlib a base64."""
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=dpi, bbox_inches='tight', transparent=True)
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")
    
    @staticmethod
    def generate_heatmap(df):
        """
        Genera un mapa de calor de correlaciones.
        
        Args:
            df: DataFrame con datos numéricos
            
        Returns:
            str: Imagen en base64 o None si no hay suficientes datos
        """
        df_numeric = df.select_dtypes(include=['float64', 'int64'])
        if df_numeric.shape[1] < 2 or df_numeric.shape[0] < 2:
            return None
        
        ChartGenerator._configure_pyplot()
        fig, ax = plt.subplots(figsize=(8, 5))
        sns.heatmap(
            df_numeric.corr(),
            annot=True,
            cmap='coolwarm',
            fmt=".2f",
            linewidths=.5,
            vmin=-1,
            vmax=1,
            ax=ax
        )
        plt.tight_layout()
        return ChartGenerator._fig_to_base64(fig)
    
    @staticmethod
    def generate_nps_chart(promotores, pasivos, detractores):
        """
        Genera un gráfico de dona para NPS.
        
        Args:
            promotores: Número de promotores
            pasivos: Número de pasivos
            detractores: Número de detractores
            
        Returns:
            str: Imagen en base64 o None si no hay datos
        """
        labels = ['Promotores', 'Pasivos', 'Detractores']
        sizes = [promotores, pasivos, detractores]
        colors = ['#10b981', '#fbbf24', '#ef4444']
        
        # Filtrar valores vacíos
        labels = [l for l, s in zip(labels, sizes) if s > 0]
        colors = [c for c, s in zip(colors, sizes) if s > 0]
        sizes = [s for s in sizes if s > 0]
        
        if not sizes:
            return None
        
        fig, ax = plt.subplots(figsize=(5, 3))
        ax.pie(
            sizes,
            labels=labels,
            autopct='%1.0f%%',
            startangle=90,
            colors=colors,
            pctdistance=0.85,
            textprops=dict(color="#333333", fontsize=10, weight='bold')
        )
        
        # Agregar círculo central para efecto dona
        centre_circle = plt.Circle((0, 0), 0.60, fc='white')
        fig.gca().add_artist(centre_circle)
        plt.tight_layout()
        
        return ChartGenerator._fig_to_base64(fig)
    
    @staticmethod
    def generate_vertical_bar_chart(labels, counts, title):
        """
        Genera un gráfico de barras verticales.
        
        Args:
            labels: Etiquetas del eje X
            counts: Valores para cada barra
            title: Título del gráfico
            
        Returns:
            str: Imagen en base64
        """
        ChartGenerator._configure_pyplot()
        fig, ax = plt.subplots(figsize=(7, 4))
        bars = ax.bar(labels, counts, color='#0d6efd', alpha=0.9, width=0.6)
        
        ax.set_title(title, fontsize=12, weight='bold', color='#111827', pad=15)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.spines['bottom'].set_color('#e5e7eb')
        ax.tick_params(axis='y', left=False, labelleft=False)
        ax.tick_params(axis='x', colors='#6b7281')
        ax.bar_label(bars, fmt='%d', padding=3, fontsize=10, color='#111827', weight='bold')
        
        plt.tight_layout()
        return ChartGenerator._fig_to_base64(fig)

    @staticmethod
    def generate_pie_chart(labels, counts, title):
        """
        Genera un gráfico de dona (pie con hueco central) para distribuciones de opciones.
        """
        ChartGenerator._configure_pyplot()
        # Filtrar valores nulos
        filtered = [(l, c) for l, c in zip(labels, counts) if c is not None and c >= 0]
        if not filtered:
            return None

        labels_f, counts_f = zip(*filtered)

        # Elegir paleta de colores
        palette = sns.color_palette('tab10' if len(labels_f) <= 10 else 'hls', n_colors=len(labels_f))
        colors = [tuple(int(x * 255) for x in p) for p in palette]
        # Convertir a hex
        colors_hex = ['#%02x%02x%02x' % c for c in colors]

        fig, ax = plt.subplots(figsize=(6, 4))
        wedges, texts, autotexts = ax.pie(
            counts_f,
            labels=labels_f,
            autopct='%1.0f%%',
            startangle=90,
            colors=colors_hex,
            pctdistance=0.75,
            textprops=dict(color="#333333", fontsize=9)
        )

        # Agregar círculo central para efecto dona
        centre_circle = plt.Circle((0, 0), 0.60, fc='white')
        fig.gca().add_artist(centre_circle)

        ax.set_title(title, fontsize=11, weight='bold', color='#111827', pad=10)
        plt.tight_layout()
        return ChartGenerator._fig_to_base64(fig)
    
    @staticmethod
    def generate_horizontal_bar_chart(labels, counts, title):
        """
        Genera un gráfico de barras horizontales.
        
        Args:
            labels: Etiquetas del eje Y
            counts: Valores para cada barra
            title: Título del gráfico
            
        Returns:
            str: Imagen en base64
        """
        ChartGenerator._configure_pyplot()
        height = max(3, len(labels) * 0.6)
        fig, ax = plt.subplots(figsize=(7, height))
        y_pos = range(len(labels))
        bars = ax.barh(y_pos, counts, color='#0d6efd', alpha=0.9, height=0.6)
        
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=10, color='#6b7281')
        ax.invert_yaxis()
        ax.set_title(title, fontsize=12, weight='bold', color='#111827', pad=15)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.tick_params(axis='x', bottom=False, labelbottom=False)
        ax.tick_params(axis='y', left=False)
        ax.bar_label(bars, fmt='%d', padding=5, fontsize=10, color='#111827', weight='bold')
        
        plt.tight_layout()
        return ChartGenerator._fig_to_base64(fig)
