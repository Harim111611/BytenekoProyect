# Core Services - Servicios de Negocio

Este subdirectorio contiene servicios reutilizables que encapsulan lógica de negocio compleja.

## Archivos

- **survey_analysis.py**: Análisis especializado de encuestas
- **test_survey_analysis.py**: Tests para análisis de encuestas

## Funcionalidad

### Analysis Service
Proporciona funciones genéricas de análisis:
- Estadísticas descriptivas
- Agregaciones de datos
- Cálculos de tendencias

```python

stats = analyze_data(survey_responses)
```

### Survey Analysis
Análisis especializado para encuestas:
- Distribución de respuestas
- Correlaciones entre preguntas
- Demografía de respondientes
- Generación de insights

```python
from core.services.survey_analysis import AnalyzeSurvey

results = survey_analysis.generate_report()
```

## Patrones

### Clean Code
- Una responsabilidad por servicio
- Métodos pequeños y testables
- Sin efectos secundarios

### Testing
```python
def test_analysis():
    data = [1, 2, 3, 4, 5]
    result = analyze_data(data)
    assert result['mean'] == 3.0
```

## Uso desde Vistas

```python
from core.services.survey_analysis import AnalyzeSurvey
from surveys.models import Survey

def survey_detail(request, survey_id):
    survey = get_object_or_404(Survey, id=survey_id)
    analyzer = AnalyzeSurvey(survey)
    analysis = analyzer.get_results_summary()
    
    return render(request, 'surveys/detail.html', {
        'survey': survey,
        'analysis': analysis
    })
```

## Performance

- Los análisis se cachean cuando es posible
- Se usan índices de base de datos
- Las queries se optimizan con select_related/prefetch_related

## Extensión

Para agregar un nuevo servicio:

```python
# services/nuevo_servicio.py
class NuevoServicio:
    def __init__(self, datos):
        self.datos = datos
    
    def procesar(self):
        return self.datos
```
