# Core Reports Templates - Generación de Reportes

Este subdirectorio contiene templates para reportes en PDF y previsualización.

## Archivos

- **reports_page.html**: Página de generación de reportes
- **report_pdf_template.html**: Template PDF para exportación
- **_report_preview_content.html**: Componente de preview
- **_global_results_pdf.html**: Componente de resultados para PDF

## reports_page.html

Página para generar y exportar reportes:
- Filtros (fechas, preguntas)
- Preview interactivo
- Botones de exportación (PDF, PPTX)
- Histórico de reportes

```html
{% extends "base/base.html" %}

{% block title %}Reportes{% endblock %}

{% block content %}
  <div class="reports-container">
    <div class="filters">
      <!-- Filtros -->
    </div>
    <div class="preview">
      {% include "core/reports/_report_preview_content.html" %}
    </div>
    <div class="export-buttons">
      <button>Descargar PDF</button>
      <button>Descargar PowerPoint</button>
    </div>
  </div>
{% endblock %}
```

## report_pdf_template.html

Template para renderizar como PDF:
- Encabezado con título
- Tabla de datos
- Gráficos
- Pie de página con fecha

## _report_preview_content.html

Componente reutilizable de preview:
- Muestra contenido que se exportará
- Actualiza con AJAX al cambiar filtros
- Estilos PDF-friendly

```html
<div class="report-preview">
  <h2>{{ survey.title }}</h2>
  <table class="results">
    <!-- Datos -->
  </table>
</div>
```

## _global_results_pdf.html

Componente global para resultados en PDF:
- Tabla consolidada
- Estadísticas
- Formato imprimible

## AJAX Integration

Preview actualizado sin recargar:

```javascript
// Al cambiar filtro
$('#date-filter').on('change', function() {
  $.ajax({
    url: '/core/reports/preview/',
    data: {
      survey_id: surveId,
      start_date: startDate,
      end_date: endDate
    },
    success: function(html) {
      $('#preview').html(html);
    }
  });
});
```

## Context Requerido

```python
context = {
    'survey': survey,
    'responses': responses,
    'stats': statistics,
    'charts': chart_data,
    'date_range': (start, end),
}
```

## Exportación

PDF:
```python
from core.reports.pdf_generator import generate_pdf
pdf_bytes = generate_pdf(survey_id, filters)
```

PowerPoint:
```python
from core.reports.pptx_generator import generate_pptx
pptx_bytes = generate_pptx(survey_id, filters)
```
