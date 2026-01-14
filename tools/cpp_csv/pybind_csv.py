import cpp_csv
import logging

logger = logging.getLogger(__name__)


def read_csv(filename, delimiter=','):
    """
    Lee un archivo CSV y regresa una lista de filas (list[list[str]]).
    """
    try:
        return cpp_csv.read_csv(filename, delimiter)
    except Exception as e:
        logger.error(f"Error leyendo CSV con cpp_csv: {e}")
        raise


def read_csv_dicts(filename, delimiter=','):
    """
    Lee un CSV y regresa una lista de diccionarios usando la primera fila 
    como encabezado.
    """
    try:
        return cpp_csv.read_csv_dicts(filename, delimiter)
    except Exception as e:
        logger.error(f"Error leyendo CSV con cpp_csv: {e}")
        raise


def read_csv_as_dicts(filename, delimiter=','):
    """
    Alias para read_csv_dicts por compatibilidad.
    Lee un CSV usando el módulo C++ y regresa una lista de diccionarios.
    """
    return read_csv_dicts(filename, delimiter)


def read_and_validate_csv(filename, schema, delimiter=','):
    """
    Lee y valida un CSV usando el módulo C++ optimizado.
    
    Args:
        filename: Ruta al archivo CSV
        schema: Diccionario con reglas de validación por columna
            Ejemplo: {
                'Edad': {'type': 'number'},
                'Satisfaccion': {'type': 'scale', 'min': 0, 'max': 10},
                'Departamento': {'type': 'single', 'options': ['Ventas', 'IT', 'RRHH']},
                'Comentarios': {'type': 'text'}
            }
        delimiter: Delimitador del CSV (por defecto ',')
    
    Returns:
        Dict con dos claves:
            'data': Lista de diccionarios con datos validados y convertidos
            'errors': Lista de errores encontrados durante la validación
    
    Tipos soportados:
        - 'text': Texto sin validación
        - 'number': Número (float/int)
        - 'scale': Número dentro de un rango (min/max)
        - 'single': Valor que debe estar en una lista de opciones válidas
    """
    try:
        return cpp_csv.read_and_validate_csv(filename, schema, delimiter)
    except Exception as e:
        logger.error(f"Error validando CSV con cpp_csv: {e}")
        raise
