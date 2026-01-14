# Core Reports - Generadores de Reportes

Este subdirectorio contiene módulos especializados para generar reportes en diferentes formatos.

## Archivos

- **pdf_generator.py**: Generación de reportes PDF usando WeasyPrint
- **pptx_generator.py**: Generación de presentaciones PowerPoint
- **test_pdf_generator.py**: Tests para PDF generator
- **test_pptx_generator.py**: Tests para PPTX generator

## Funcionalidad

### PDF Generator
Genera reportes en PDF con:
- Tablas de datos
- Gráficos integrados
- Estilos personalizados
- Encabezados y pies de página

```python
from core.reports.pdf_generator import generate_pdf

pdf_bytes = generate_pdf(survey_id, user=request.user)
```

### PPTX Generator
Genera presentaciones PowerPoint con:
- Portada con título
- Diapositivas de contenido
- Gráficos y tablas
- Estilos profesionales

```python
from core.reports.pptx_generator import generate_pptx

pptx_bytes = generate_pptx(survey_id, user=request.user)
```

## Templates Utilizados

Los generadores usan templates HTML que se renderean:
- `core/reports/report_document.html`
- `core/reports/_report_preview_content.html`
- `core/reports/_global_results_pdf.html`

## Testing

Ejecutar tests de reportes:

```bash
pytest core/reports/test_pdf_generator.py -v
pytest core/reports/test_pptx_generator.py -v
```

## Dependencias

- **WeasyPrint**: Para generación de PDF
- **python-pptx**: Para generación de PowerPoint
- **Django Template Engine**: Para renderear HTML

## Optimización

- Los PDFs se generan bajo demanda
- Los reportes se cachean cuando es posible
- Las imágenes se comprimen automáticamente
