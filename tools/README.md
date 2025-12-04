# Tools - Herramientas Especializadas

Este directorio contiene herramientas y utilidades especializadas para el proyecto.

## Contenido

- **check_analysis.py**: Verificar datos de análisis
- **cpp_csv/**: Módulo compilado para procesamiento rápido de CSV

## check_analysis.py

Script para verificar integridad de datos de análisis:

```bash
python tools/check_analysis.py
```

### Funcionalidad
- Valida datos de análisis
- Detecta inconsistencias
- Genera reportes

## cpp_csv/

Módulo compilado (C++) para procesamiento de CSV de alto rendimiento.

### Uso
```python
from tools.cpp_csv import CSVProcessor

processor = CSVProcessor()
data = processor.read_fast('datos.csv')
```

### Ventajas
- Procesamiento 10x más rápido
- Manejo de archivos grandes
- Bajo uso de memoria

### Compilación
```bash
# Solo si es necesario recompilar
python setup.py build_ext --inplace
```

## Extensión

Agregar nueva herramienta:

```python
# tools/mi_herramienta.py
def procesar_datos():
    """Descripción de la herramienta."""
    pass

if __name__ == '__main__':
    procesar_datos()
```

## Ejecución

```bash
# Como script
python tools/mi_herramienta.py

# Como módulo
from tools import mi_herramienta
mi_herramienta.procesar_datos()
```

## Performance

Herramientas optimizadas para:
- Procesamiento masivo de datos
- Análisis complejos
- Exportación rápida
