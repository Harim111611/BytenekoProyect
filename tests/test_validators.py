"""
Tests unitarios para core/validators.py
Verifica que todas las validaciones funcionen correctamente con datos válidos e inválidos
"""
import pytest
from django.core.exceptions import ValidationError
from datetime import date

from core.validators import (
    DateFilterValidator,
    SurveyValidator,
    CSVImportValidator,
    ResponseValidator
)


class TestDateFilterValidator:
    """Tests para DateFilterValidator"""
    
    def test_validate_date_string_valid(self):
        """Debe aceptar fechas en formato YYYY-MM-DD"""
        result = DateFilterValidator.validate_date_string('2024-12-25')
        assert result == date(2024, 12, 25)
    
    def test_validate_date_string_none(self):
        """Debe retornar None si la fecha es None o vacía"""
        assert DateFilterValidator.validate_date_string(None) is None
        assert DateFilterValidator.validate_date_string('') is None
    
    def test_validate_date_string_invalid_format(self):
        """Debe rechazar formatos inválidos"""
        with pytest.raises(ValidationError, match="Formato de fecha inválido"):
            DateFilterValidator.validate_date_string('25-12-2024')
        
        with pytest.raises(ValidationError):
            DateFilterValidator.validate_date_string('2024/12/25')
        
        with pytest.raises(ValidationError):
            DateFilterValidator.validate_date_string('invalid')
    
    def test_validate_window_days_valid(self):
        """Debe aceptar números enteros positivos"""
        assert DateFilterValidator.validate_window_days('30') == 30
        assert DateFilterValidator.validate_window_days('1') == 1
        assert DateFilterValidator.validate_window_days('365') == 365
    
    def test_validate_window_days_none(self):
        """Debe retornar None si es None o vacío"""
        assert DateFilterValidator.validate_window_days(None) is None
        assert DateFilterValidator.validate_window_days('') is None
    
    def test_validate_window_days_invalid(self):
        """Debe rechazar valores no numéricos"""
        with pytest.raises(ValidationError, match="debe ser un número entero positivo"):
            DateFilterValidator.validate_window_days('abc')
        
        with pytest.raises(ValidationError):
            DateFilterValidator.validate_window_days('30.5')
    
    def test_validate_window_days_zero_or_negative(self):
        """Debe rechazar 0 y negativos"""
        with pytest.raises(ValidationError, match="debe ser mayor que 0"):
            DateFilterValidator.validate_window_days('0')
        
        with pytest.raises(ValidationError):
            DateFilterValidator.validate_window_days('-5')
    
    def test_validate_window_days_too_large(self):
        """Debe rechazar valores mayores a 10 años"""
        with pytest.raises(ValidationError, match="no puede ser mayor a 3650"):
            DateFilterValidator.validate_window_days('5000')
    
    def test_validate_date_range_valid(self):
        """Debe aceptar rangos lógicos"""
        start = date(2024, 1, 1)
        end = date(2024, 12, 31)
        DateFilterValidator.validate_date_range(start, end)  # No debe lanzar excepción
    
    def test_validate_date_range_invalid(self):
        """Debe rechazar fecha inicio posterior a fecha fin"""
        start = date(2024, 12, 31)
        end = date(2024, 1, 1)
        with pytest.raises(ValidationError, match="no puede ser posterior"):
            DateFilterValidator.validate_date_range(start, end)
    
    def test_validate_date_range_none_values(self):
        """Debe aceptar None en alguno de los valores"""
        DateFilterValidator.validate_date_range(None, date(2024, 12, 31))
        DateFilterValidator.validate_date_range(date(2024, 1, 1), None)
        DateFilterValidator.validate_date_range(None, None)


class TestSurveyValidator:
    """Tests para SurveyValidator"""
    
    def test_validate_survey_id_valid(self):
        """Debe aceptar IDs enteros positivos"""
        assert SurveyValidator.validate_survey_id('123') == 123
        assert SurveyValidator.validate_survey_id('1') == 1
        assert SurveyValidator.validate_survey_id(456) == 456
    
    def test_validate_survey_id_none_or_empty(self):
        """Debe rechazar None o vacío"""
        with pytest.raises(ValidationError, match="ID de encuesta faltante"):
            SurveyValidator.validate_survey_id(None)
        
        with pytest.raises(ValidationError):
            SurveyValidator.validate_survey_id('')
    
    def test_validate_survey_id_invalid(self):
        """Debe rechazar valores inválidos"""
        with pytest.raises(ValidationError, match="ID de encuesta inválido"):
            SurveyValidator.validate_survey_id('abc')
        
        with pytest.raises(ValidationError):
            SurveyValidator.validate_survey_id('0')
        
        with pytest.raises(ValidationError):
            SurveyValidator.validate_survey_id('-5')
    
    def test_validate_boolean_param_true_values(self):
        """Debe reconocer diversos formatos de 'true'"""
        assert SurveyValidator.validate_boolean_param('true', 'test') is True
        assert SurveyValidator.validate_boolean_param('True', 'test') is True
        assert SurveyValidator.validate_boolean_param('1', 'test') is True
        assert SurveyValidator.validate_boolean_param('yes', 'test') is True
        assert SurveyValidator.validate_boolean_param('on', 'test') is True
        assert SurveyValidator.validate_boolean_param(True, 'test') is True
    
    def test_validate_boolean_param_false_values(self):
        """Debe reconocer diversos formatos de 'false'"""
        assert SurveyValidator.validate_boolean_param('false', 'test') is False
        assert SurveyValidator.validate_boolean_param('False', 'test') is False
        assert SurveyValidator.validate_boolean_param('0', 'test') is False
        assert SurveyValidator.validate_boolean_param('no', 'test') is False
        assert SurveyValidator.validate_boolean_param('off', 'test') is False
        assert SurveyValidator.validate_boolean_param(False, 'test') is False
    
    def test_validate_boolean_param_none_default(self):
        """Debe retornar True por defecto si es None"""
        assert SurveyValidator.validate_boolean_param(None, 'test') is True
    
    def test_validate_boolean_param_invalid(self):
        """Debe rechazar valores inválidos"""
        with pytest.raises(ValidationError, match="Parámetro 'test' inválido"):
            SurveyValidator.validate_boolean_param('invalid', 'test')


class TestCSVImportValidator:
    """Tests para CSVImportValidator"""
    
    def test_validate_csv_file_none(self):
        """Debe rechazar None"""
        with pytest.raises(ValidationError, match="No se proporcionó ningún archivo"):
            CSVImportValidator.validate_csv_file(None)
    
    def test_validate_csv_file_wrong_extension(self):
        """Debe rechazar extensiones no CSV"""
        class FakeFile:
            name = 'data.xlsx'
            size = 1024
        
        with pytest.raises(ValidationError, match="Solo se permiten archivos .csv"):
            CSVImportValidator.validate_csv_file(FakeFile())
    
    def test_validate_csv_file_too_large(self):
        """Debe rechazar archivos mayores a 10MB"""
        class FakeFile:
            name = 'data.csv'
            size = 11 * 1024 * 1024  # 11MB
        
        with pytest.raises(ValidationError, match="demasiado grande"):
            CSVImportValidator.validate_csv_file(FakeFile())
    
    def test_validate_csv_file_valid(self):
        """Debe aceptar archivos CSV válidos"""
        class FakeFile:
            name = 'data.csv'
            size = 5 * 1024 * 1024  # 5MB
        
        file = FakeFile()
        result = CSVImportValidator.validate_csv_file(file)
        assert result == file
    
    def test_validate_dataframe_empty(self):
        """Debe rechazar DataFrames vacíos"""
        import pandas as pd
        
        with pytest.raises(ValidationError, match="está vacío"):
            CSVImportValidator.validate_dataframe(None)
        
        with pytest.raises(ValidationError):
            CSVImportValidator.validate_dataframe(pd.DataFrame())
    
    def test_validate_dataframe_too_many_columns(self):
        """Debe rechazar más de 100 columnas"""
        import pandas as pd
        
        df = pd.DataFrame({f'col{i}': [1] for i in range(101)})
        with pytest.raises(ValidationError, match="demasiadas columnas"):
            CSVImportValidator.validate_dataframe(df)
    
    def test_validate_dataframe_too_many_rows(self):
        """Debe rechazar más de 10,000 filas"""
        import pandas as pd
        
        df = pd.DataFrame({'col1': range(10001)})
        with pytest.raises(ValidationError, match="demasiadas filas"):
            CSVImportValidator.validate_dataframe(df)
    
    def test_validate_dataframe_valid(self):
        """Debe aceptar DataFrames válidos"""
        import pandas as pd
        
        df = pd.DataFrame({'col1': [1, 2, 3], 'col2': [4, 5, 6]})
        result = CSVImportValidator.validate_dataframe(df)
        assert result.equals(df)
    
    def test_validate_column_name_empty(self):
        """Debe rechazar nombres vacíos"""
        with pytest.raises(ValidationError, match="columnas sin nombre"):
            CSVImportValidator.validate_column_name('')
        
        with pytest.raises(ValidationError):
            CSVImportValidator.validate_column_name('   ')
    
    def test_validate_column_name_too_long(self):
        """Debe rechazar nombres mayores a 500 caracteres"""
        long_name = 'a' * 501
        with pytest.raises(ValidationError, match="demasiado largo"):
            CSVImportValidator.validate_column_name(long_name)
    
    def test_validate_column_name_valid(self):
        """Debe aceptar y limpiar nombres válidos"""
        assert CSVImportValidator.validate_column_name('  Column 1  ') == 'Column 1'
        assert CSVImportValidator.validate_column_name('Valid_Name') == 'Valid_Name'


class TestResponseValidator:
    """Tests para ResponseValidator"""
    
    def test_validate_numeric_response_valid(self):
        """Debe aceptar números válidos"""
        assert ResponseValidator.validate_numeric_response('42') == 42.0
        assert ResponseValidator.validate_numeric_response(3.14) == 3.14
        assert ResponseValidator.validate_numeric_response(-5) == -5.0
    
    def test_validate_numeric_response_invalid(self):
        """Debe rechazar valores no numéricos"""
        with pytest.raises(ValidationError, match="Valor numérico inválido"):
            ResponseValidator.validate_numeric_response('abc')
    
    def test_validate_numeric_response_with_range(self):
        """Debe validar rangos min/max"""
        # Dentro del rango
        assert ResponseValidator.validate_numeric_response('5', min_val=0, max_val=10) == 5.0
        
        # Fuera del rango (menor)
        with pytest.raises(ValidationError, match="menor que el mínimo"):
            ResponseValidator.validate_numeric_response('-5', min_val=0, max_val=10)
        
        # Fuera del rango (mayor)
        with pytest.raises(ValidationError, match="mayor que el máximo"):
            ResponseValidator.validate_numeric_response('15', min_val=0, max_val=10)
    
    def test_validate_scale_response_valid(self):
        """Debe aceptar valores de escala 1-10"""
        assert ResponseValidator.validate_scale_response('1') == 1.0
        assert ResponseValidator.validate_scale_response('5') == 5.0
        assert ResponseValidator.validate_scale_response('10') == 10.0
    
    def test_validate_scale_response_invalid(self):
        """Debe rechazar valores fuera de 1-10"""
        with pytest.raises(ValidationError, match="menor que el mínimo"):
            ResponseValidator.validate_scale_response('0')
        
        with pytest.raises(ValidationError, match="mayor que el máximo"):
            ResponseValidator.validate_scale_response('11')
    
    def test_validate_text_response_valid(self):
        """Debe aceptar y limpiar texto válido"""
        assert ResponseValidator.validate_text_response('  Hello  ') == 'Hello'
        assert ResponseValidator.validate_text_response('Valid text') == 'Valid text'
    
    def test_validate_text_response_empty(self):
        """Debe retornar cadena vacía para None o vacío"""
        assert ResponseValidator.validate_text_response(None) == ''
        assert ResponseValidator.validate_text_response('') == ''
    
    def test_validate_text_response_too_long(self):
        """Debe rechazar texto mayor a 5000 caracteres"""
        long_text = 'a' * 5001
        with pytest.raises(ValidationError, match="demasiado larga"):
            ResponseValidator.validate_text_response(long_text)
    
    def test_validate_text_response_custom_max_length(self):
        """Debe respetar max_length personalizado"""
        short_text = 'a' * 50
        assert ResponseValidator.validate_text_response(short_text, max_length=100) == short_text
        
        with pytest.raises(ValidationError):
            ResponseValidator.validate_text_response(short_text, max_length=10)
