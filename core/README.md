# Core - Funcionalidad Base del Proyecto

Este módulo contiene la lógica central y las utilidades compartidas del proyecto.

## Estructura

### Archivos Principales

- **models.py**: Modelos base de datos compartidos
- **views.py**: Vistas generales y middlewares
- **urls.py**: Rutas específicas de core
- **admin.py**: Configuración del panel de administración
- **apps.py**: Configuración de la app
- **validators.py**: Validadores reutilizables

### Middleware

- **middleware.py**: Middlewares generales del proyecto
- **middleware_logging.py**: Sistema de logging personalizado
- **views_ratelimit.py**: Control de límite de velocidad (rate limiting)

### Mixins

- **mixins.py**: Clases mixtas para modelos y vistas reutilizables

### Directorios

#### `/migrations/`
Migraciones de base de datos de Django. Se generan automáticamente y versionan cambios en modelos.

#### `/services/`
Lógica de negocio reutilizable:
- `survey_analysis.py`: Análisis específico de encuestas

#### `/utils/`
Funciones de utilidad:
- `charts.py`: Generación de gráficos
- `helpers.py`: Funciones auxiliares comunes
- `logging_utils.py`: Utilidades de logging

#### `/reports/`
Generación de reportes:
- `pdf_generator.py`: Generación de PDFs con WeasyPrint
- `pptx_generator.py`: Generación de presentaciones PowerPoint

## Funcionalidad

### Rate Limiting
Controla el número de solicitudes por usuario/IP:
```python
from core.views_ratelimit import rate_limit_view
```

### Logging
Sistema centralizado de logging:
```python
from core.utils.logging_utils import log_activity
```

### Análisis
Servicios de análisis de encuestas:
```python
from core.services.survey_analysis import analyze_survey
```

### Reportes
Generación de reportes en múltiples formatos:
```python
from core.reports.pdf_generator import generate_pdf
from core.reports.pptx_generator import generate_pptx
```

## Testing

Los tests están ubicados en `/tests/` en la raíz del proyecto.
