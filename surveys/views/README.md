# Surveys Views - Vistas del Módulo Surveys

Este subdirectorio contiene las vistas (controladores HTTP) organizadas por funcionalidad.

## Archivos

- **crud_views.py**: Operaciones CRUD (Create, Read, Update, Delete)
- **import_views.py**: Importación de datos desde archivos
- **question_views.py**: Gestión de preguntas
- **report_views.py**: Generación y visualización de reportes
- **respond_views.py**: Vistas para responder encuestas

## Funcionalidad

### CRUD Views
Operaciones básicas sobre encuestas:
- **SurveyListView**: Listar encuestas del usuario
- **SurveyDetailView**: Ver detalles de una encuesta
- **SurveyCreateView**: Crear nueva encuesta
- **SurveyUpdateView**: Editar encuesta
- **SurveyDeleteView**: Eliminar encuesta

### Import Views
Importación masiva de datos:
- **CSVImportView**: Importar respuestas desde CSV
- **ImportJobListView**: Historial de importaciones
- **ImportJobDetailView**: Detalles de importación

### Question Views
Gestión de preguntas:
- **QuestionCreateView**: Crear pregunta
- **QuestionUpdateView**: Editar pregunta
- **QuestionDeleteView**: Eliminar pregunta

### Report Views
Análisis y reportes:
- **SurveyResultsView**: Ver resultados de encuesta
- **GeneratePDFView**: Exportar a PDF
- **GeneratePPTXView**: Exportar a PowerPoint
- **ReportFilterView**: Filtrar y analizar resultados

### Respond Views
Interfaz pública para responder:
- **PublicSurveyView**: Página para responder
- **SubmitResponseView**: Guardar respuesta
- **ThankYouView**: Página de agradecimiento

## Patrones

### Vistas Basadas en Clases (CBV)
```python
from django.views import ListView, DetailView
from surveys.models import Survey

class SurveyListView(ListView):
    model = Survey
    template_name = 'surveys/crud/list.html'
    context_object_name = 'surveys'
    paginate_by = 20
```

### Vistas Basadas en Funciones (FBV)
```python
from django.shortcuts import render
from surveys.models import Survey

def survey_detail(request, survey_id):
    survey = get_object_or_404(Survey, id=survey_id)
    return render(request, 'surveys/crud/detail.html', {
        'survey': survey
    })
```

## Seguridad

- Validación de permisos
- Solo el creador puede ver/editar sus encuestas
- CSRF protection activado
- Limpieza de entrada de usuario

## Performance

- `select_related()` para relaciones
- `prefetch_related()` para relaciones inversas
- Paginación de resultados
- Caché de análisis

## Testing

```bash
pytest surveys/views/ -v
pytest surveys/views/test_crud_views.py -v
```

## URLs Asociadas

```python
# surveys/urls.py
urlpatterns = [
    # CRUD
    path('list/', SurveyListView.as_view(), name='list'),
    path('<int:survey_id>/', SurveyDetailView.as_view(), name='detail'),
    path('create/', SurveyCreateView.as_view(), name='create'),
    
    # Responder
    path('<slug:public_id>/respond/', PublicSurveyView.as_view(), name='respond'),
    
    # Reportes
    path('<int:survey_id>/results/', SurveyResultsView.as_view(), name='results'),
]
```

## Estructura Recomendada

Cada vista debe:
1. Validar permisos
2. Obtener datos con queries optimizadas
3. Procesar datos si es necesario
4. Pasar contexto a template
5. Manejar errores apropiadamente
