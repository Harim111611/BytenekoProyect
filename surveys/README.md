# Surveys - Módulo de Encuestas

Este módulo contiene toda la lógica relacionada con la creación, gestión y respuesta de encuestas.

## Estructura

### Archivos Principales

- **models.py**: Modelos de encuestas, preguntas y respuestas
- **forms.py**: Formularios de Django para encuestas
- **admin.py**: Configuración del panel administrativo
- **apps.py**: Configuración de la aplicación
- **signals.py**: Señales de Django para eventos automáticos
- **tasks.py**: Tareas asincrónicas con Celery
- **urls.py**: Rutas específicas de encuestas
- **validators.py**: Validadores personalizados

### Directorios

#### `/views/`
Vistas organizadas por funcionalidad:
- `crud_views.py`: Operaciones CRUD (Crear, Leer, Actualizar, Eliminar) de encuestas
- `import_views.py`: Importación masiva de datos desde CSV
- `question_views.py`: Gestión de preguntas
- `report_views.py`: Generación de reportes de encuestas
- `respond_views.py`: Vistas para responder encuestas

#### `/utils/`
Funciones auxiliares específicas de encuestas

#### `/static/`
Archivos estáticos (CSS, JavaScript, imágenes) específicos de encuestas

#### `/management/`
Comandos personalizados de Django:
- `commands/`: Directorio de comandos management

#### `/migrations/`
Migraciones de base de datos para los modelos de encuestas

#### `/tests/`
Tests unitarios para encuestas (movidos a `/tests/` raíz)

## Flujo de Trabajo

### 1. Crear Encuesta
```python
from surveys.models import Survey
survey = Survey.objects.create(
    title="Mi Encuesta",
    description="Descripción"
)
```

### 2. Agregar Preguntas
```python
from surveys.models import Question
question = Question.objects.create(
    survey=survey,
    text="¿Pregunta?",
    question_type="choice"
)
```

### 3. Importar Respuestas (CSV)
Usar la vista de import para cargar datos masivamente desde CSV.

### 4. Analizar Resultados
Las tareas de Celery procesan análisis en background.

### 5. Generar Reportes
Exportar a PDF o PowerPoint usando las vistas de reporte.

## Tareas Asincrónicas

Las tareas definidas en `tasks.py` se ejecutan con Celery:
- Procesamiento de importaciones
- Generación de reportes
- Análisis de datos

```python
from surveys.tasks import process_survey_import
process_survey_import.delay(survey_id)
```

## Modelos Principales

- **Survey**: Encuesta principal
- **Question**: Preguntas dentro de encuestas
- **Answer**: Respuestas a preguntas
- **AnswerOption**: Opciones de respuesta para preguntas de elección
- **ImportJob**: Registro de importaciones masivas
