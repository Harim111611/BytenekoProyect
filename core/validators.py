"""
Validadores personalizados para el módulo core
Centraliza la lógica de validación para mantener consistencia
"""
from datetime import datetime
from django.core.exceptions import ValidationError


class DateFilterValidator:
    """Valida filtros de fecha para reportes."""
    
    @staticmethod
    def validate_date_string(date_str, field_name="fecha"):
        """Valida que un string de fecha tenga formato correcto."""
        if not date_str:
            return None
        
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            return date_obj
        except ValueError:
            raise ValidationError(
                f"Formato de {field_name} inválido. Use YYYY-MM-DD (ej: 2024-12-31)"
            )
    
    @staticmethod
    def validate_window_days(window_str):
        """Valida que el window_days sea un número positivo o 'all'."""
        if not window_str:
            return None
        
        # Permitir 'all' como valor especial para mostrar todos los datos
        if window_str.lower() == 'all':
            return 'all'
        
        if not window_str.isdigit():
            raise ValidationError(
                "El parámetro 'window_days' debe ser un número entero positivo o 'all'"
            )
        
        days = int(window_str)
        if days <= 0:
            raise ValidationError(
                "El parámetro 'window_days' debe ser mayor que 0"
            )
        
        if days > 3650:  # Máximo 10 años
            raise ValidationError(
                "El parámetro 'window_days' no puede ser mayor a 3650 días (10 años)"
            )
        
        return days
    
    @staticmethod
    def validate_date_range(start_date, end_date):
        """Valida que el rango de fechas sea lógico."""
        if start_date and end_date and start_date > end_date:
            raise ValidationError(
                "La fecha de inicio no puede ser posterior a la fecha de fin"
            )


class SurveyValidator:
    """Validadores para encuestas."""
    
    @staticmethod
    def validate_survey_id(survey_id):
        """Valida que el ID de encuesta sea válido."""
        if not survey_id:
            raise ValidationError("ID de encuesta faltante")
        
        try:
            survey_id = int(survey_id)
            if survey_id <= 0:
                raise ValueError
            return survey_id
        except (ValueError, TypeError):
            raise ValidationError(
                f"ID de encuesta inválido: '{survey_id}'. Debe ser un número entero positivo"
            )
    
    @staticmethod
    def validate_boolean_param(param_value, param_name):
        """Valida parámetros booleanos de tipo 'true'/'false'."""
        if param_value is None:
            return True  # Default
        
        if isinstance(param_value, bool):
            return param_value
        
        if isinstance(param_value, str):
            lower_val = param_value.lower()
            if lower_val in ('true', '1', 'yes', 'on'):
                return True
            if lower_val in ('false', '0', 'no', 'off'):
                return False
        
        raise ValidationError(
            f"Parámetro '{param_name}' inválido: '{param_value}'. Use 'true' o 'false'"
        )


class CSVImportValidator:
    """Validadores para importación de CSV."""
    
    @staticmethod
    def validate_csv_file(csv_file):
        """Valida que el archivo sea un CSV válido."""
        if not csv_file:
            raise ValidationError("No se proporcionó ningún archivo CSV")
        
        # Verificar extensión
        filename = csv_file.name.lower()
        if not filename.endswith('.csv'):
            raise ValidationError(
                f"Formato de archivo inválido: '{csv_file.name}'. Solo se permiten archivos .csv"
            )
        
        # Verificar tamaño (máximo 10MB)
        max_size = 10 * 1024 * 1024  # 10MB en bytes
        if csv_file.size > max_size:
            size_mb = csv_file.size / (1024 * 1024)
            raise ValidationError(
                f"El archivo es demasiado grande ({size_mb:.1f}MB). Tamaño máximo: 10MB"
            )
        
        return csv_file
    
    @staticmethod
    def validate_dataframe(df):
        """Valida que el DataFrame tenga estructura válida."""
        if df is None or df.empty:
            raise ValidationError("El archivo CSV está vacío")
        
        if len(df.columns) == 0:
            raise ValidationError("El archivo CSV no tiene columnas")
        
        if len(df) == 0:
            raise ValidationError("El archivo CSV no tiene filas de datos")
        
        # Detectar si es un CSV de resumen/agregados en lugar de respuestas individuales
        suspicious_columns = ['indicador', 'valor', 'tipo', 'formato', 'métrica', 'promedio', 'total']
        if len(df.columns) <= 4 and any(col.lower() in suspicious_columns for col in df.columns):
            raise ValidationError(
                "Este archivo parece ser un resumen de datos. "
                "El sistema necesita un CSV con respuestas individuales de encuestas, donde:\n"
                "• Cada fila = una respuesta de un usuario\n"
                "• Cada columna = una pregunta\n"
                "• Los valores = las respuestas dadas\n\n"
                "Ejemplo correcto:\n"
                "Usuario,Edad,Satisfacción,Producto Favorito\n"
                "Juan,25,8,Laptop\n"
                "María,30,9,Mouse"
            )
        
        # Validar que no haya demasiadas columnas
        if len(df.columns) > 100:
            raise ValidationError(
                f"El CSV tiene demasiadas columnas ({len(df.columns)}). Máximo permitido: 100"
            )
        
        # Validar que no haya demasiadas filas
        if len(df) > 10000:
            raise ValidationError(
                f"El CSV tiene demasiadas filas ({len(df)}). Máximo permitido: 10,000"
            )
        
        return df
    
    @staticmethod
    def validate_column_name(col_name):
        """Valida que el nombre de columna sea válido."""
        if not col_name or not str(col_name).strip():
            raise ValidationError("El CSV contiene columnas sin nombre")
        
        if len(str(col_name)) > 500:
            raise ValidationError(
                f"Nombre de columna demasiado largo: '{col_name[:50]}...'. Máximo: 500 caracteres"
            )
        
        return str(col_name).strip()


class ResponseValidator:
    """Validadores para respuestas de encuestas."""
    
    @staticmethod
    def validate_numeric_response(value, min_val=None, max_val=None):
        """Valida que una respuesta numérica esté en rango."""
        try:
            num_value = float(value)
        except (ValueError, TypeError):
            raise ValidationError(
                f"Valor numérico inválido: '{value}'"
            )
        
        if min_val is not None and num_value < min_val:
            raise ValidationError(
                f"El valor {num_value} es menor que el mínimo permitido ({min_val})"
            )
        
        if max_val is not None and num_value > max_val:
            raise ValidationError(
                f"El valor {num_value} es mayor que el máximo permitido ({max_val})"
            )
        
        return num_value
    
    @staticmethod
    def validate_scale_response(value):
        """Valida respuesta de tipo escala (1-10)."""
        return ResponseValidator.validate_numeric_response(value, min_val=1, max_val=10)
    
    @staticmethod
    def validate_text_response(value, max_length=5000):
        """Valida respuesta de texto."""
        if not value:
            return ""
        
        text = str(value).strip()
        if len(text) > max_length:
            raise ValidationError(
                f"Respuesta de texto demasiado larga ({len(text)} caracteres). Máximo: {max_length}"
            )
        
        return text
