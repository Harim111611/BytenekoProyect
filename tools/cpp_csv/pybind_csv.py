import cpp_csv


def read_csv_as_dicts(filename, delimiter=','):
    """
    Lee un CSV usando el módulo C++ y regresa una lista de diccionarios.
    La primera fila del archivo se usa como encabezado.
    """
    return cpp_csv.read_csv_dicts(filename, delimiter)


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
    return cpp_csv.read_and_validate_csv(filename, schema, delimiter)
