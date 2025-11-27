# core/utils.py
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import io
import base64


def generate_heatmap_chart(df):
    # Verificar si hay suficientes columnas numéricas
    df_numeric = df.select_dtypes(include=['float64', 'int64'])
    if df_numeric.shape[1] < 2 or df_numeric.shape[0] < 2:
        return None

    plt.style.use('default')
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['Arial'],
        'font.size': 9
    })
    fig, ax = plt.subplots(figsize=(8, 5))

    # Calcular correlación solo con datos numéricos
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

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches='tight', transparent=True)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def generate_nps_chart(prom, pas, det):
    labels = ['Promotores', 'Pasivos', 'Detractores']
    sizes = [prom, pas, det]
    colors = ['#10b981', '#fbbf24', '#ef4444']

    # Filtrar vacíos para que no se rompa el gráfico
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
    centre_circle = plt.Circle((0, 0), 0.60, fc='white')
    fig.gca().add_artist(centre_circle)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches='tight', transparent=True)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def generate_vertical_bar_chart(labels, counts, title):
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Arial']})
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
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, transparent=True)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def generate_horizontal_bar_chart(labels, counts, title):
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Arial']})
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
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, transparent=True)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")