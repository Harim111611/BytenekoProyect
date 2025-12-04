# Surveys Utils - Utilidades del Módulo Surveys

Este subdirectorio contiene funciones auxiliares específicas para el módulo de encuestas.

## Archivos

- **helpers.py**: Funciones auxiliares para encuestas
- **validators.py**: Validadores específicos de encuestas
- Otros módulos de utilidad según sea necesario

## Funcionalidad

### Helpers
Funciones auxiliares para operaciones comunes:
- Formateo de datos de encuestas
- Conversión de formatos
- Utilidades de importación/exportación
- Generación de IDs únicos

```python
from surveys.utils.helpers import generate_survey_id, format_response

survey_id = generate_survey_id()
formatted = format_response(response_data)
```

### Validators
Validación especializada para encuestas:
- Validación de respuestas
- Validación de preguntas
- Validación de archivos CSV
- Límites y restricciones

```python
from surveys.utils.validators import validate_survey_response

is_valid, errors = validate_survey_response(response_data, survey)
```

## Uso desde Vistas

```python
from surveys.utils.helpers import parse_csv_file
from surveys.utils.validators import validate_csv_format

def import_responses(request, survey_id):
    file = request.FILES['csv_file']
    
    # Validar formato
    is_valid, errors = validate_csv_format(file)
    if not is_valid:
        return JsonResponse({'errors': errors})
    
    # Procesar
    data = parse_csv_file(file)
    
    return JsonResponse({'status': 'success'})
```

## Uso desde Servicios

```python
from surveys.utils.validators import validate_survey_data
from core.services.survey_analysis import AnalyzeSurvey

def process_survey(survey_data):
    # Validar datos
    valid, errors = validate_survey_data(survey_data)
    if not valid:
        raise ValueError(f"Datos inválidos: {errors}")
    
    # Analizar
    survey = Survey.objects.create(**survey_data)
    analyzer = AnalyzeSurvey(survey)
    return analyzer.generate_report()
```

## Mejores Prácticas

- **Validación temprana**: Validar en las vistas
- **Mensajes claros**: Errores descriptivos
- **Reutilización**: Funciones genéricas
- **Testing**: Cobertura completa

## Testing

```bash
pytest surveys/utils/test_helpers.py -v
pytest surveys/utils/test_validators.py -v
```

## Extensión

Agregar nueva utilidad:

```python
# surveys/utils/formatters.py
def format_survey_title(title):
    """Formatea el título de la encuesta."""
    return title.strip().title()
```
