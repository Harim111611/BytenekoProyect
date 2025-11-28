
# --- IMPORTS Y LOGGER ---
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect, get_object_or_404
import pandas as pd
import json
from datetime import datetime
from surveys.models import Survey, Question, AnswerOption, SurveyResponse, QuestionResponse
from core.validators import CSVImportValidator, ResponseValidator
from core.utils.logging_utils import StructuredLogger, log_performance, log_user_action, log_data_change
from surveys.utils.bulk_import import bulk_import_responses_postgres

logger = StructuredLogger('surveys')


from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
import pandas as pd
from datetime import datetime
import logging

from surveys.models import Survey, Question, AnswerOption, SurveyResponse, QuestionResponse
from surveys.utils.bulk_import import bulk_import_responses_postgres
from core.utils.logging_utils import log_user_action, log_data_change

logger = logging.getLogger(__name__)

# ============================================================
# FUNCIONES DE IMPORTACIÓN/EXPORTACIÓN
# ============================================================

@login_required
@ratelimit(key='user', rate='5/h', method='POST', block=True)
def import_survey_view(request):
    """
    Importación CSV optimizada con PostgreSQL COPY FROM.
    """
    # ...existing code...
    return redirect('surveys:list')


@login_required
@ratelimit(key='user', rate='10/h', method='POST', block=True)
def import_csv_preview_view(request):
    """Vista AJAX para generar preview del CSV antes de importar."""
    from django.http import JsonResponse
    import pandas as pd
    from core.validators import CSVImportValidator
    if request.method == 'POST' and request.FILES.get('csv_file'):
        try:
            csv_file = CSVImportValidator.validate_csv_file(request.FILES.get('csv_file'))
            encodings = [
                'utf-8-sig', 'utf-8', 'utf-16', 'utf-16-le', 'utf-16-be',
                'latin-1', 'iso-8859-1', 'cp1252', 'windows-1252', 'mac_roman'
            ]
            df = None
            for encoding in encodings:
                try:
                    csv_file.seek(0)
                    df = pd.read_csv(csv_file, encoding=encoding)
                    break
                except Exception:
                    continue
            if df is None or df.empty:
                return JsonResponse({'success': False, 'error': 'El archivo CSV está vacío o no se pudo leer.', 'columns': [], 'total_rows': 0, 'total_columns': 0, 'filename': csv_file.name, 'sample_rows': []}, status=400)
            try:
                df = CSVImportValidator.validate_dataframe(df)
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e), 'columns': [], 'total_rows': 0, 'total_columns': 0, 'filename': csv_file.name, 'sample_rows': []}, status=400)
            preview_data = {
                'success': True,
                'filename': csv_file.name,
                'total_rows': len(df),
                'total_columns': len(df.columns),
                'columns': [],
                'sample_rows': []
            }
            for col in df.columns:
                col_info = {
                    'name': col,
                    'display_name': col.replace('_', ' ').title(),
                    'type': 'text',
                    'unique_values': 0,
                    'sample_values': [],
                    'is_metadata': False
                }
                sample = df[col].dropna()
                if pd.api.types.is_numeric_dtype(sample):
                    if not sample.empty and sample.min() >= 0 and sample.max() <= 10:
                        col_info['type'] = 'scale'
                    else:
                        col_info['type'] = 'number'
                else:
                    if sample.astype(str).str.contains(',').any():
                        col_info['type'] = 'multi'
                    elif sample.nunique() < 15:
                        col_info['type'] = 'single'
                col_info['unique_values'] = sample.nunique()
                col_info['sample_values'] = [str(v) for v in sample.unique()[:3]]
                preview_data['columns'].append(col_info)
            preview_data['sample_rows'] = [
                [str(val) if not pd.isna(val) else '' for val in row]
                for row in df.head(5).values.tolist()
            ]
            return JsonResponse(preview_data)
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Error inesperado: {str(e)[:200]}', 'columns': [], 'total_rows': 0, 'total_columns': 0, 'filename': '', 'sample_rows': []}, status=500)
    return JsonResponse({'error': 'Method not allowed', 'columns': []}, status=405)


@login_required
@ratelimit(key='user', rate='100/h', method='POST', block=True)
def import_multiple_surveys_view(request):
    """Vista para importar múltiples archivos CSV a la vez."""
    from django.http import JsonResponse
    # ...existing code...
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)


@login_required
def import_responses_view(request, pk):
    return redirect('surveys:detail', pk=pk)
