# Data Samples - Datos de Ejemplo para Testing

Este directorio contiene datos de ejemplo para uso en testing y desarrollo.

## Contenido

Muestras de datos en diferentes formatos:

- **CSV**: Archivos para importación de datos
- **JSON**: Datos serializados
- **SQL**: Dumps de base de datos (opcional)

## Archivos Comunes

- `sample_survey.csv`: Encuesta de ejemplo
- `sample_responses.csv`: Respuestas de ejemplo
- `sample_data.json`: Datos JSON de ejemplo
- Otros archivos según necesidad

## Uso en Testing

### Cargar datos de ejemplo
```python
from django.core.management import call_command

class SurveyTestCase(TestCase):
    def setUp(self):
        call_command('loaddata', 'samples/sample_data.json')
```

### Usar archivos CSV
```python
import csv

def test_csv_import():
    with open('data/samples/sample_responses.csv') as f:
        reader = csv.DictReader(f)
        data = list(reader)
```

## Crear Nuevas Muestras

```bash
# Exportar datos como fixture
python manage.py dumpdata surveys --indent 2 > data/samples/surveys.json

# Crear CSV manualmente
# O usar un script en scripts/

# Limitar tamaño
# Usar datasets pequeños para tests rápidos
```

## Estructura de Datos

### Survey Sample CSV
```csv
title,description,status,created_at
Encuesta 1,Descripción 1,active,2024-01-01
Encuesta 2,Descripción 2,draft,2024-01-02
```

### Responses Sample CSV
```csv
survey_id,question_id,response,respondent_id
1,1,Opción A,1001
1,2,5,1001
2,1,Opción B,1002
```

## Mejores Prácticas

1. **Datos realistas**: Usar datos similares a producción
2. **Pequeños datasets**: Tests más rápidos
3. **Variedad**: Incluir casos normal, edge, error
4. **Documentación**: Explicar qué contiene cada archivo
5. **Versionado**: Mantener en git

## Migración desde Producción

```bash
# Exportar datos anonymizados
python manage.py dumpdata \
  --exclude auth.permission \
  --exclude contenttypes \
  --indent 2 > data/samples/production_sample.json
```

## Privacy

⚠️ **IMPORTANTE**: 
- Nunca incluir datos personales reales
- Anonymizar emails, teléfonos
- Usar datos ficticios
- Revisar antes de commit
