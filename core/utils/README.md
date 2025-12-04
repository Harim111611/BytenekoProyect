# Core Utils - Utilidades y Funciones Auxiliares

Este subdirectorio contiene funciones reutilizables de utilidad para el módulo core y otros módulos.

## Archivos

- **charts.py**: Generación de gráficos
- **helpers.py**: Funciones auxiliares comunes
- **logging_utils.py**: Utilidades de logging
- **test_charts.py**: Tests para gráficos
- **test_logging_utils.py**: Tests para logging

## Funcionalidad

### Charts
Generación de gráficos usando Matplotlib/Seaborn:
- Gráficos de barras
- Gráficos de líneas
- Diagramas circulares
- Gráficos de distribución

```python
from core.utils.charts import generate_bar_chart

chart = generate_bar_chart(data, title="Mi Gráfico")
```

### Helpers
Funciones auxiliares reutilizables:
- Formateo de datos
- Conversión de tipos
- Validación de entrada
- Paginación

```python
from core.utils.helpers import format_phone, slugify_text

formatted = format_phone("+1234567890")
slug = slugify_text("Mi Título")
```

### Logging Utils
Sistema de logging personalizado:
- Logging estructurado
- Niveles configurables
- Formateo personalizado

```python
from core.utils.logging_utils import log_activity, log_error

log_activity(user, "Descargó reporte", survey)
log_error("Error al generar PDF", exception)
```

## Uso

### Desde Vistas
```python
from core.utils.helpers import paginate_list
from core.utils.charts import generate_bar_chart

def survey_results(request, survey_id):
    survey = Survey.objects.get(id=survey_id)
    responses = survey.responses.all()
    
    # Paginar
    page = paginate_list(responses, request.GET.get('page', 1), 10)
    
    # Generar gráfico
    chart_data = {
        'labels': ['Opción A', 'Opción B'],
        'values': [50, 30]
    }
    chart = generate_bar_chart(chart_data)
    
    return render(request, 'surveys/results.html', {
        'page': page,
        'chart': chart
    })
```

### Desde Servicios
```python
from core.utils.helpers import normalize_data
from core.services.survey_analysis import AnalyzeSurvey

def analyze_survey(survey):
    raw_data = survey.get_raw_responses()
    normalized = normalize_data(raw_data)
    analyzer = AnalyzeSurvey(survey)
    return analyzer.analyze(normalized)
```

## Testing

```bash
pytest core/utils/test_charts.py -v
pytest core/utils/test_logging_utils.py -v
```

## Mejores Prácticas

- **DRY**: No repetir código
- **Simple**: Funciones pequeñas
- **Testeable**: Fácil de probar
- **Documentado**: Docstrings claros

## Extensión

Agregar nueva utilidad:

```python
# core/utils/validators.py
def validate_email(email):
    """Valida un email."""
    return '@' in email and '.' in email
```
