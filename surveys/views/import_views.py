import logging
import pandas as pd
from datetime import datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

# Modelos
from surveys.models import Survey, Question, AnswerOption

# Utilidades y Validadores
from surveys.utils.bulk_import import bulk_import_responses_postgres
from core.validators import CSVImportValidator
# Si usas el decorador de performance, asegúrate que existe en core.utils.logging_utils
# Si no, puedes quitar la línea @log_performance
try:
    from core.utils.logging_utils import log_performance
except ImportError:
    # Fallback dummy decorator si no existe
    def log_performance(**kwargs):
        def decorator(func):
            return func
        return decorator

logger = logging.getLogger(__name__)

# ============================================================
# HELPER INTERNO: PROCESAR UN SOLO CSV
# ============================================================
def _process_single_csv_import(csv_file, user, override_title=None):
    """
    Lógica central para procesar un archivo CSV y crear una encuesta.
    Retorna (Survey, rows_count, answers_count) o lanza Exception.
    """
    # 1. Validar archivo
    CSVImportValidator.validate_csv_file(csv_file)

    # 2. Leer DataFrame (probar varios encodings)
    encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
    df = None
    
    for encoding in encodings:
        try:
            csv_file.seek(0)
            df = pd.read_csv(csv_file, encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
            
    if df is None:
        raise ValidationError(f"No se pudo leer el archivo {csv_file.name}. Verifique la codificación.")

    # 3. Validar estructura del DataFrame
    df = CSVImportValidator.validate_dataframe(df)
    
    # 4. Determinar título
    title = override_title if override_title else csv_file.name.replace('.csv', '').replace('_', ' ').title()

    # 5. Crear Estructura y Datos (Transacción Atómica)
    with transaction.atomic():
        # A. Crear Encuesta
        survey = Survey.objects.create(
            title=title[:255],
            description=f"Importado automáticamente desde {csv_file.name}",
            status='active',
            author=user
        )

        # B. Crear Preguntas y Opciones (Inferencia de tipos)
        questions_map = {}
        
        for idx, col_name in enumerate(df.columns):
            sample = df[col_name].dropna()
            question_type = 'text' # Default
            
            # Lógica de inferencia
            if pd.api.types.is_numeric_dtype(sample):
                if not sample.empty and sample.min() >= 0 and sample.max() <= 10:
                    question_type = 'scale'
                else:
                    question_type = 'number'
            else:
                if sample.astype(str).str.contains(',').any():
                    question_type = 'multi'
                elif sample.nunique() < 20:
                    question_type = 'single'

            # Crear Pregunta
            question = Question.objects.create(
                survey=survey,
                text=col_name[:500],
                type=question_type,
                order=idx
            )

            # Preparar metadatos para importación masiva
            col_data = {
                'question': question,
                'dtype': question_type,
                'options': {}
            }

            # Crear Opciones si aplica
            if question_type in ['single', 'multi']:
                unique_options = set()
                if question_type == 'multi':
                    for items in sample.astype(str):
                        for item in items.split(','):
                            unique_options.add(item.strip())
                else:
                    unique_options = set(sample.astype(str).unique())

                for i, opt_text in enumerate(sorted(unique_options)):
                    if not opt_text.strip(): continue
                    option = AnswerOption.objects.create(
                        question=question,
                        text=opt_text[:255],
                        order=i
                    )
                    col_data['options'][opt_text] = option # Guardar referencia para map

            questions_map[col_name] = col_data

        # C. Importación Masiva de Respuestas
        total_rows, imported_answers = bulk_import_responses_postgres(survey, df, questions_map)
        
        return survey, total_rows, imported_answers


# ============================================================
# VISTAS
# ============================================================

@login_required
@require_POST
@ratelimit(key='user', rate='10/h', method='POST', block=True)
@log_performance(threshold_ms=5000)
def import_survey_view(request):
    """
    Importa un UNICO archivo CSV.
    Retorna JSON para integración con el frontend.
    """
    csv_file = request.FILES.get('csv_file')
    survey_title = request.POST.get('survey_title')

    if not csv_file:
        return JsonResponse({'success': False, 'error': 'No se recibió ningún archivo.'}, status=400)

    try:
        survey, rows, _ = _process_single_csv_import(csv_file, request.user, survey_title)
        
        messages.success(request, f"¡Éxito! Encuesta '{survey.title}' creada con {rows} respuestas.")
        
        return JsonResponse({
            'success': True,
            'redirect_url': f"/surveys/{survey.id}/results/"
        })

    except Exception as e:
        logger.error(f"Error importando {csv_file.name}: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_POST
@ratelimit(key='user', rate='20/h', method='POST', block=True)
def import_multiple_surveys_view(request):
    """
    Importa MÚLTIPLES archivos CSV a la vez.
    """
    files = request.FILES.getlist('csv_files')
    
    if not files:
        return JsonResponse({'success': False, 'error': 'No se recibieron archivos.'}, status=400)

    results = []
    errors = []
    success_count = 0

    for csv_file in files:
        try:
            # Procesar cada archivo individualmente
            survey, rows, _ = _process_single_csv_import(csv_file, request.user)
            results.append(f"✅ {csv_file.name}: {rows} respuestas")
            success_count += 1
        except Exception as e:
            logger.error(f"Error en carga masiva ({csv_file.name}): {e}")
            errors.append(f"❌ {csv_file.name}: {str(e)}")

    # Mensaje final al usuario
    if success_count > 0:
        msg = f"Se importaron {success_count} encuesta(s) correctamente."
        messages.success(request, msg)
    
    if errors:
        messages.warning(request, "Hubo errores en algunos archivos. Revisa el reporte.")

    return JsonResponse({
        'success': success_count > 0,
        'imported_count': success_count,
        'all_errors': errors,
        'details': results
    })


@login_required
@ratelimit(key='user', rate='20/h', method='POST', block=True)
def import_csv_preview_view(request):
    """
    Genera una vista previa de la estructura del CSV sin guardar nada en BD.
    """
    csv_file = request.FILES.get('csv_file')
    if not csv_file:
        return JsonResponse({'success': False, 'error': 'Falta archivo'}, status=400)

    try:
        # Validación ligera solo para leer
        CSVImportValidator.validate_csv_file(csv_file)
        
        # Leer dataframe
        encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
        df = None
        for encoding in encodings:
            try:
                csv_file.seek(0)
                df = pd.read_csv(csv_file, encoding=encoding)
                break
            except Exception:
                continue
        
        if df is None:
            return JsonResponse({'success': False, 'error': 'Archivo ilegible'}, status=400)

        df = CSVImportValidator.validate_dataframe(df)

        # Construir respuesta de preview
        preview = {
            'success': True,
            'filename': csv_file.name,
            'total_rows': len(df),
            'total_columns': len(df.columns),
            'columns': [],
            'sample_rows': []
        }

        for col in df.columns:
            sample = df[col].dropna()
            col_type = 'text'
            
            if pd.api.types.is_numeric_dtype(sample):
                if not sample.empty and sample.min() >= 0 and sample.max() <= 10:
                    col_type = 'scale'
                else:
                    col_type = 'number'
            elif sample.astype(str).str.contains(',').any():
                col_type = 'multi'
            elif sample.nunique() < 20:
                col_type = 'single'

            preview['columns'].append({
                'name': col,
                'display_name': col.replace('_', ' ').title(),
                'type': col_type,
                'unique_values': sample.nunique(),
                'sample_values': [str(v) for v in sample.unique()[:3]]
            })

        # Primeras 5 filas como muestra (convertidas a string para JSON)
        preview['sample_rows'] = df.head(5).astype(object).where(pd.notnull(df), "").astype(str).values.tolist()

        return JsonResponse(preview)

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def import_responses_view(request, pk):
    """Placeholder para importar respuestas a una encuesta existente"""
    return redirect('surveys:detail', pk=pk)