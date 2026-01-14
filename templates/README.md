# Templates - Plantillas HTML

Este directorio contiene los templates (plantillas HTML) de la aplicación, organizados por funcionalidad y módulo.

## Estructura

```
templates/
├── base/                       # Templates base
│   ├── base.html               # Template base principal
│   └── app_base.html           # Template base alternativo
│
├── core/                       # Templates del módulo core
│   ├── dashboard/              # Vistas de dashboard
│   │   ├── dashboard.html      # Dashboard principal
│   │   ├── results_dashboard.html  # Dashboard de resultados
│   │   ├── settings.html       # Página de configuración
│   │   └── ratelimit_error.html    # Error de rate limit
│   │
│   └── reports/                # Generación de reportes
│       ├── reports_page.html   # Página de reportes
│       ├── report_document.html  # Template para PDF
│       ├── _global_results_pdf.html  # Componente de resultados PDF
│       └── _report_preview_content.html  # Preview de reportes
│
├── surveys/                    # Templates del módulo surveys
│   ├── crud/                   # Operaciones CRUD
│   │   ├── list.html           # Listado de encuestas
│   │   ├── detail.html         # Detalle de encuesta
│   │   ├── encuesta_detail.html    # Detalle alternativo
│   │   ├── confirm_delete.html # Confirmación de eliminación
│   │   └── not_found.html      # Encuesta no encontrada
│   │
│   ├── forms/                  # Formularios
│   │   ├── form.html           # Formulario genérico
│   │   └── survey_create.html  # Crear nueva encuesta
│   │
│   ├── responses/              # Respuesta de encuestas
│   │   ├── fill.html           # Formulario para responder
│   │   ├── thanks.html         # Página de agradecimiento
│   │   └── results.html        # Resultados de encuesta
│   │
│   ├── modals/                 # Modales de confirmación
│   │   ├── delete_all_modal.html   # Eliminar todo
│   │   ├── delete_one_modal.html   # Eliminar uno
│   │   └── delete_selected_modal.html  # Eliminar seleccionados
│   │
│   └── components/             # Componentes reutilizables
│       ├── _toast_delete.html  # Notificación de eliminación
│       └── _toast_feedback.html    # Notificación genérica
│
├── shared/                     # Templates compartidos
│   ├── index.html              # Página de inicio
│   └── login.html              # Página de login
│
└── errors/                     # Páginas de error
    ├── 404.html                # Error 404 no encontrado
    └── 500.html                # Error 500 servidor
```

## Convenciones de Naming

### Templates Principales
- Nombres descriptivos en minúsculas con guiones: `dashboard.html`, `survey_create.html`
- Un word por nivel: `reports_page.html`

### Componentes y Parciales
- Prefijo con guión bajo: `_toast_delete.html`, `_report_preview_content.html`
- Indican que son fragmentos reutilizables

### Directorios
- Por funcionalidad: `dashboard/`, `reports/`, `crud/`
- Por rol: `responses/` para templates de usuario respondiendo
- Nombres en minúsculas: `forms/`, `components/`, `modals/`

## Herencia de Templates

Todos los templates heredan de `base/base.html`:

```html
{% extends "base/base.html" %}

{% block title %}Mi Página{% endblock %}

{% block content %}
  <!-- Contenido específico -->
{% endblock %}
```

## Inclusión de Componentes

Los componentes parciales se incluyen con:

```html
{% include "surveys/components/_toast_delete.html" %}
```

## Django Template Language (DTL)

Sintaxis común:

- **Variables**: `{{ variable }}`
- **Filtros**: `{{ variable|default:"valor" }}`
- **Bucles**: `{% for item in items %}...{% endfor %}`
- **Condicionales**: `{% if condition %}...{% endif %}`
- **Herencia**: `{% extends "base/base.html" %}`
- **Bloques**: `{% block name %}...{% endblock %}`

## Archivos Estáticos en Templates

```html
{% load static %}
<link rel="stylesheet" href="{% static 'css/style.css' %}">
<script src="{% static 'js/app.js' %}"></script>
<img src="{% static 'images/logo.png' %}" alt="Logo">
```

## Context Processors

Variables globales disponibles en todos los templates:
- `user`: Usuario actual
- `request`: Objeto request
- Configuraciones personalizadas

## Optimización

- Usar `{% cache %}` para secciones estáticas
- Minimizar SQL queries con `select_related()` y `prefetch_related()`
- Usar `{% spaceless %}` para reducir espacios en blanco
- Delegar lógica compleja a Python (vistas/services)

## Patrones Comunes

### Dashboard
```html
{% extends "base/base.html" %}
{% block title %}Dashboard{% endblock %}
{% block content %}
  <div class="container">
    <!-- Contenido del dashboard -->
  </div>
{% endblock %}
```

### Modal
```html
<div class="modal" id="myModal">
  <div class="modal-content">
    <!-- Contenido -->
  </div>
</div>
```

### Toast/Notificación
```html
<div class="toast alert-success">
  Operación completada exitosamente
</div>
```

## Testing de Templates

Para testear templates:

```python
from django.test import TestCase
from django.template.loader import render_to_string

class TemplateTest(TestCase):
    def test_template_render(self):
        html = render_to_string('surveys/crud/list.html', {
            'surveys': []
        })
        self.assertIn('Encuestas', html)
```
