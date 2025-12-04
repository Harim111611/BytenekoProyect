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
    def generate_heatmap(df, dark_mode=False):
        """
        Genera un mapa de calor de correlaciones.
        
        Args:
            df: DataFrame con datos numéricos
            dark_mode: Si True, genera gráfico optimizado para fondo oscuro
            
        Returns:
            str: Imagen en base64 o None si no hay suficientes datos
        """
        if df is None or df.empty:
            return None
            
        # Seleccionar columnas numéricas
        df_numeric = df.select_dtypes(include=['float64', 'int64', 'float32', 'int32'])
        
        # Si no hay columnas numéricas, intentar convertir
        if df_numeric.empty:
            df_numeric = df.copy()
            for col in df_numeric.columns:
                try:
                    df_numeric[col] = pd.to_numeric(df_numeric[col], errors='coerce')
                except:
                    pass
            df_numeric = df_numeric.select_dtypes(include=['float64', 'int64', 'float32', 'int32'])
        
        # Verificar que haya suficientes datos
        if df_numeric.shape[1] < 2 or df_numeric.shape[0] < 2:
            return None
        
        # Eliminar columnas que solo tienen NaN
        df_numeric = df_numeric.dropna(axis=1, how='all')
        
        # Verificar nuevamente después de limpiar
        if df_numeric.shape[1] < 2 or df_numeric.shape[0] < 2:
            return None
        
        ChartGenerator._configure_pyplot()
        
        # Calcular correlación
        corr_matrix = df_numeric.corr()
        
        # Verificar que la matriz de correlación no esté vacía
        if corr_matrix.empty or corr_matrix.shape[0] < 2:
            return None
        
        # Acortar nombres de columnas para mejor visualización
        def truncate_label(text, max_length=30):
            """Trunca texto largo y elimina prefijos comunes."""
            text = str(text)
            # Eliminar prefijos comunes de preguntas
            prefixes = ['¿Qué tan ', '¿Cómo ', '¿Cuál ', '¿Por qué ', '¿Dónde ', '¿Cuándo ']
            for prefix in prefixes:
                if text.startswith(prefix):
                    text = text[len(prefix):]
            
            # Eliminar sufijos comunes
            if text.endswith('?'):
                text = text[:-1]
            
            # Truncar si es muy largo
            if len(text) > max_length:
                text = text[:max_length-3] + '...'
            
            return text
        
        # Renombrar columnas y filas
        short_labels = [truncate_label(col) for col in corr_matrix.columns]
        corr_matrix.columns = short_labels
        corr_matrix.index = short_labels
        
        # Calcular tamaño dinámico basado en número de preguntas
        n_questions = corr_matrix.shape[0]
        fig_width = max(8, min(14, n_questions * 2.5))
        fig_height = max(6, min(12, n_questions * 2))
        
        # Configuración de colores según el tema
        if dark_mode:
            bg_color = '#1f2937'
            text_color = '#e5e7eb'
            title_color = '#f9fafb'
            line_color = '#374151'
            cmap = 'RdYlGn'  # Mantener el mismo esquema de colores
        else:
            bg_color = 'white'
            text_color = '#374151'
            title_color = '#1f2937'
            line_color = 'white'
            cmap = 'RdYlGn'
        
        fig, ax = plt.subplots(figsize=(fig_width, fig_height), facecolor=bg_color)
        ax.set_facecolor(bg_color)
        
        # Generar heatmap con mejor formato
        sns.heatmap(
            corr_matrix,
            annot=True,
            cmap=cmap,
            fmt=".2f",
            linewidths=1,
            linecolor=line_color,
            vmin=-1,
            vmax=1,
            ax=ax,
            cbar_kws={
                'label': 'Coeficiente de Correlación',
                'shrink': 0.8,
                'pad': 0.02
            },
            square=True,  # Celdas cuadradas
            annot_kws={'size': 10, 'weight': 'bold'}
        )
        
        # Configurar título
        ax.set_title(
            'Mapa de Correlaciones entre Variables', 
            fontsize=14, 
            weight='bold', 
            pad=20,
            color=title_color
        )
        
        # Rotar etiquetas para mejor legibilidad
        ax.set_xticklabels(
            ax.get_xticklabels(),
            rotation=45,
            ha='right',
            fontsize=9,
            color=text_color
        )
        ax.set_yticklabels(
            ax.get_yticklabels(),
            rotation=0,
            fontsize=9,
            color=text_color
        )
        
        # Configurar colorbar para modo oscuro
        cbar = ax.collections[0].colorbar
        cbar.ax.yaxis.label.set_color(text_color)
        cbar.ax.tick_params(colors=text_color)
        
        # Mejorar el espaciado
        plt.tight_layout()
        
        return ChartGenerator._fig_to_base64(fig, dpi=120)
    
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
        
        # Usar figura cuadrada para evitar distorsión de la dona
        fig, ax = plt.subplots(figsize=(5, 5))
        ax.pie(
            sizes,
            labels=labels,
            autopct='%1.0f%%',
            startangle=90,
            colors=colors,
            pctdistance=0.85,
            textprops=dict(color="#333333", fontsize=10, weight='bold')
        )
        # Asegurar aspecto igual para que el círculo no se aplaste
        ax.axis('equal')
        
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

        # Figura cuadrada para mantener proporción en dona
        fig, ax = plt.subplots(figsize=(5.5, 5.5))
        wedges, texts, autotexts = ax.pie(
            counts_f,
            labels=labels_f,
            autopct='%1.0f%%',
            startangle=90,
            colors=colors_hex,
            pctdistance=0.75,
            textprops=dict(color="#333333", fontsize=9)
        )
        # Asegurar aspecto igual para que el círculo no se aplaste
        ax.axis('equal')

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
