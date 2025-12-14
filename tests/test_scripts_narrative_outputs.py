import os
from narrative_utils_standalone import NumericNarrative, DemographicNarrative, TextMiningEngine

# Archivos de prueba
csv_files = [
    'data/samples/encuesta_satisfaccion_universitaria.csv',
    'data/samples/encuesta_satisfaccion_clientes.csv',
    'data/samples/encuesta_hotel_huespedes.csv',
    'data/samples/encuesta_hospital_servicios.csv',
    'data/samples/encuesta_clima_laboral.csv',
    'data/samples/correlacion_demo.csv',
    'data/samples/test_import.csv',
]

# Columnas que suelen ser numéricas, categóricas o texto
NUMERIC_HINTS = ['calificacion', 'puntaje', 'satisfaccion', 'escala', 'nps', 'edad', 'tiempo', 'confort', 'limpieza', 'infraestructura', 'balance', 'liderazgo', 'recursos', 'desarrollo', 'comunicacion']
CATEGORICAL_HINTS = ['tipo', 'area', 'carrera', 'plan', 'servicio', 'genero', 'nacionalidad', 'habitacion', 'recomendaria', 'volveria']
TEXT_HINTS = ['comentario', 'sugerencia', 'opinion', 'feedback', 'descripcion']


def detect_column_type(col):
    col_l = col.lower()
    if any(h in col_l for h in NUMERIC_HINTS):
        return 'numeric'
    if any(h in col_l for h in CATEGORICAL_HINTS):
        return 'categorical'
    if any(h in col_l for h in TEXT_HINTS):
        return 'text'
    return 'unknown'


def analyze_csv(path):
    print(f'\n===== Análisis para: {os.path.basename(path)} =====')
    df = pd.read_csv(path)
    total = len(df)
    for col in df.columns:
        col_type = detect_column_type(col)
        values = df[col].dropna()
        if col_type == 'numeric':
            try:
                vals = pd.to_numeric(values, errors='coerce').dropna()
                if len(vals) == 0:
                    continue
                avg = vals.mean()
                max_val = vals.max()
                print(f'\n--- Numérico: {col} ---')
                print(NumericNarrative.analyze(avg, max_val, n_sentences=3))
            except Exception as e:
                print(f'Error numérico en {col}: {e}')
        elif col_type == 'categorical':
            dist = values.value_counts().reset_index()
            dist.columns = ['option', 'count']
            dist = dist.to_dict('records')
            if len(dist) == 0:
                continue
            print(f'\n--- Categórico: {col} ---')
            print(DemographicNarrative.analyze(dist, total, col, col, n_sentences=3))
        elif col_type == 'text':
            texts = [str(v) for v in values if isinstance(v, str) and v.strip()]
            if not texts:
                continue
            print(f'\n--- Texto: {col} ---')
            topics, sentiment = TextMiningEngine.extract_topics_and_sentiment(texts)
            intro = f"Se leyeron {len(texts)} comentarios. "
            temas = f"La gente habló mucho de: {', '.join(topics[:5])}. " if topics else "No hubo temas que se repitan mucho. "
            sent = f"En general, el sentimiento es **{sentiment}**. "
            if sentiment == "Positivo":
                interpret = "A la mayoría le gustó lo que recibió."
            elif sentiment == "Negativo":
                interpret = "A varios no les gustó y hay cosas para mejorar."
            else:
                interpret = "Hay opiniones de todo tipo, no hay una sola idea."
            recomend = "Leer los comentarios ayuda a ver qué se puede mejorar o mantener."
            insight_txt = intro + temas + sent + interpret + " " + recomend
            print(insight_txt)

if __name__ == '__main__':
    for csv in csv_files:
        if os.path.exists(csv):
            analyze_csv(csv)
        else:
            print(f'Archivo no encontrado: {csv}')
