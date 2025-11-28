# Vista para cambiar el estado de la encuesta (draft, active, closed)
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from .models import Survey
from django.db.models import Q

@login_required
@require_POST
def cambiar_estado_encuesta(request, pk=None):
    try:
        survey = get_object_or_404(Survey, pk=pk, author=request.user)
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
        nuevo_estado = data.get('status', data.get('estado'))
        if nuevo_estado not in ['draft', 'active', 'closed']:
            return JsonResponse({'success': False, 'error': 'Estado inválido.'}, status=400)
        survey.status = nuevo_estado
        survey.save(update_fields=['status'])
        return JsonResponse({'success': True, 'new_status': survey.status})
    except Survey.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Encuesta no encontrada o sin permisos.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
# Stubs for import_views, report_views, respond_views to satisfy imports in surveys/urls.py
# Stubs for import_views, report_views, respond_views to satisfy imports in surveys/urls.py
class ImportViews:
    @staticmethod
    def import_responses_view(request, pk=None):
        pass
    @staticmethod
    def import_survey_view(request):
        from django.http import JsonResponse
        import pandas as pd
        from core.validators import CSVImportValidator
        from surveys.utils.bulk_import import bulk_import_responses_postgres
        from django.db import transaction
        from datetime import datetime
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
                    return JsonResponse({'success': False, 'error': 'El archivo CSV está vacío o no se pudo leer.'}, status=400)
                try:
                    df = CSVImportValidator.validate_dataframe(df)
                except Exception as e:
                    return JsonResponse({'success': False, 'error': str(e)}, status=400)
                # Detect advanced/long format
                advanced_cols = {'survey_title', 'question_text', 'question_type', 'option_text', 'response_value'}
                if advanced_cols.issubset(df.columns):
                    surveys_created = 0
                    answers_created = 0
                    for survey_title, group in df.groupby('survey_title'):
                        survey = Survey.objects.create(
                            author=request.user,
                            title=survey_title,
                            description=group['survey_description'].iloc[0] if 'survey_description' in group.columns else '',
                            status='draft',
                            category=group['survey_category'].iloc[0] if 'survey_category' in group.columns else 'General'
                        )
                        questions_map = {}
                        for q_text, q_group in group.groupby('question_text'):
                            q_type = q_group['question_type'].iloc[0]
                            question = Question.objects.create(
                                survey=survey,
                                text=q_text,
                                type=q_type,
                                order=len(questions_map),
                                is_required=True
                            )
                            options = {}
                            if q_type in ['single', 'multi']:
                                for opt_text in q_group['option_text'].dropna().unique():
                                    opt = AnswerOption.objects.create(question=question, text=opt_text)
                                    options[str(opt_text)] = opt.id
                            questions_map[q_text] = {
                                'question': question,
                                'dtype': q_type,
                                'options': options
                            }
                        pivot_cols = [c for c in ['question_text', 'response_value'] if c in group.columns]
                        responses_df = group[pivot_cols].pivot(columns='question_text', values='response_value') if set(pivot_cols) == set(['question_text', 'response_value']) else None
                        if responses_df is not None:
                            responses_df = responses_df.fillna('')
                            import_cols = [c for c in responses_df.columns if c in questions_map]
                            import_df = responses_df[import_cols] if import_cols else responses_df
                            s_created, a_created = bulk_import_responses_postgres(survey, import_df, questions_map)
                            surveys_created += s_created
                            answers_created += a_created
                    return JsonResponse({'success': True, 'surveys_created': surveys_created, 'answers_created': answers_created})
                # FLAT FORMAT: One column per question, one row per response
                title = csv_file.name.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').title()
                if len(title) > 255:
                    title = title[:252] + '...'
                with transaction.atomic():
                    survey = Survey.objects.create(
                        author=request.user,
                        title=title,
                        description=f"Imported {datetime.now().strftime('%Y-%m-%d')}",
                        status='active',
                        sample_goal=len(df)
                    )
                    col_map = {}
                    skip_patterns = [
                        'response_id', 'respuesta_id', 'id_respuesta',
                        'timestamp', 'creado', 'created_at', 'updated_at',
                        'usuario', 'user', 'email', 'nombre', 'name', 'apellido', 'cliente', 'estudiante',
                        'empleado', 'paciente', 'huesped', 'telefono', 'phone', 'dni', 'cedula', 'identificacion', 'documento'
                    ]
                    for i, col in enumerate(df.columns):
                        col_name = CSVImportValidator.validate_column_name(col)
                        col_lower = col_name.lower()
                        if col_lower == 'id' or any(p in col_lower for p in skip_patterns):
                            continue
                        sample = df[col].dropna()
                        dtype = 'text'
                        if pd.api.types.is_numeric_dtype(sample):
                            dtype = 'scale' if sample.min() >= 0 and sample.max() <= 10 else 'number'
                        elif not sample.empty:
                            if sample.astype(str).str.contains(',').any():
                                dtype = 'multi'
                            elif sample.nunique() < 15:
                                dtype = 'single'
                        question = Question.objects.create(
                            survey=survey,
                            text=col_name,
                            type=dtype,
                            order=len(col_map),
                            is_required=False
                        )
                        options = {}
                        if dtype == 'single':
                            for val in sample.unique():
                                if pd.notna(val):
                                    opt = AnswerOption.objects.create(question=question, text=str(val))
                                    options[str(val)] = opt.id
                        elif dtype == 'multi':
                            unique_opts = set()
                            for val in sample:
                                if pd.notna(val):
                                    for opt in str(val).split(','):
                                        opt_clean = opt.strip()
                                        if opt_clean:
                                            unique_opts.add(opt_clean)
                            for opt_val in unique_opts:
                                opt = AnswerOption.objects.create(question=question, text=opt_val)
                                options[opt_val] = opt.id
                        col_map[col] = {
                            'question': question,
                            'dtype': dtype,
                            'options': options
                        }
                    import_cols = [c for c in df.columns if c in col_map]
                    import_df = df[import_cols].fillna('') if import_cols else df
                    s_created, a_created = bulk_import_responses_postgres(survey, import_df, col_map)
                return JsonResponse({'success': True, 'surveys_created': 1, 'answers_created': a_created})
            except Exception as e:
                return JsonResponse({'success': False, 'error': f'Error inesperado: {str(e)[:200]}'}, status=500)
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    @staticmethod
    def import_csv_preview_view(request):
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
    @staticmethod
    def import_multiple_surveys_view(request):
        return import_multiple_surveys_view(request)

# Move the decorated view outside the class
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
@login_required
@require_POST
def import_multiple_surveys_view(request):
    """
    Import multiple surveys from uploaded CSV files.
    Supports both flat (one column per question) and advanced (long) formats.
    """
    from django.http import JsonResponse
    import pandas as pd
    from core.validators import CSVImportValidator
    from surveys.utils.bulk_import import bulk_import_responses_postgres
    import traceback

    if request.method == 'POST':
        files = request.FILES.getlist('csv_files')
        if not files:
            return JsonResponse({'success': False, 'error': 'No file uploaded.'}, status=400)

        total_surveys_created = 0
        total_answers_created = 0
        all_errors = []

        for file in files:
            try:
                # Try to read CSV with encoding fallback
                encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
                df = None
                for enc in encodings:
                    try:
                        file.seek(0)
                        df = pd.read_csv(file, encoding=enc)
                        break
                    except Exception:
                        continue
                if df is None or df.empty:
                    all_errors.append(f"The uploaded file '{file.name}' is empty or unreadable.")
                    continue

                # Validate DataFrame structure (not summary, not too big)
                try:
                    df = CSVImportValidator.validate_dataframe(df)
                except Exception as e:
                    all_errors.append(f"File '{file.name}': {str(e)}")
                    continue

                # Detect advanced/long format (has survey_title, question_text, etc)
                advanced_cols = {'survey_title', 'question_text', 'question_type', 'option_text', 'response_value'}
                if advanced_cols.issubset(df.columns):
                    # Robust advanced import logic (tolerant to missing columns/questions/options)
                    surveys_created = 0
                    answers_created = 0
                    for survey_title, group in df.groupby('survey_title'):
                        survey = Survey.objects.create(
                            author=request.user,
                            title=survey_title,
                            description=group['survey_description'].iloc[0] if 'survey_description' in group.columns else '',
                            status='draft',
                            category=group['survey_category'].iloc[0] if 'survey_category' in group.columns else 'General'
                        )
                        questions_map = {}
                        for q_text, q_group in group.groupby('question_text'):
                            q_type = q_group['question_type'].iloc[0]
                            question = Question.objects.create(
                                survey=survey,
                                text=q_text,
                                type=q_type,
                                order=len(questions_map),
                                is_required=True
                            )
                            options = {}
                            if q_type in ['single', 'multi']:
                                for opt_text in q_group['option_text'].dropna().unique():
                                    opt = AnswerOption.objects.create(question=question, text=opt_text)
                                    options[str(opt_text)] = opt.id
                            questions_map[q_text] = {
                                'question': question,
                                'dtype': q_type,
                                'options': options
                            }
                        # Pivot only columns that exist, fill missing with ''
                        pivot_cols = [c for c in ['question_text', 'response_value'] if c in group.columns]
                        responses_df = group[pivot_cols].pivot(columns='question_text', values='response_value') if set(pivot_cols) == set(['question_text', 'response_value']) else None
                        if responses_df is not None:
                            responses_df = responses_df.fillna('')
                            # Only keep columns that are mapped
                            import_cols = [c for c in responses_df.columns if c in questions_map]
                            import_df = responses_df[import_cols] if import_cols else responses_df
                            s_created, a_created = bulk_import_responses_postgres(survey, import_df, questions_map)
                            surveys_created += s_created
                            answers_created += a_created
                    total_surveys_created += surveys_created
                    total_answers_created += answers_created
                    continue

                # FLAT FORMAT: One column per question, one row per response
                # Auto-detect question types and create survey/questions/options
                title = file.name.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').title()
                if len(title) > 255:
                    title = title[:252] + '...'
                with transaction.atomic():
                    survey = Survey.objects.create(
                        author=request.user,
                        title=title,
                        description=f"Imported {datetime.now().strftime('%Y-%m-%d')}",
                        status='active',
                        sample_goal=len(df)
                    )
                    col_map = {}
                    skip_patterns = [
                        'response_id', 'respuesta_id', 'id_respuesta',
                        'timestamp', 'creado', 'created_at', 'updated_at',
                        'usuario', 'user', 'email', 'nombre', 'name', 'apellido', 'cliente', 'estudiante',
                        'empleado', 'paciente', 'huesped', 'telefono', 'phone', 'dni', 'cedula', 'identificacion', 'documento'
                    ]
                    for i, col in enumerate(df.columns):
                        col_name = CSVImportValidator.validate_column_name(col)
                        col_lower = col_name.lower()
                        if col_lower == 'id' or any(p in col_lower for p in skip_patterns):
                            continue
                        sample = df[col].dropna()
                        dtype = 'text'
                        if pd.api.types.is_numeric_dtype(sample):
                            dtype = 'scale' if sample.min() >= 0 and sample.max() <= 10 else 'number'
                        elif not sample.empty:
                            if sample.astype(str).str.contains(',').any():
                                dtype = 'multi'
                            elif sample.nunique() < 15:
                                dtype = 'single'
                        question = Question.objects.create(
                            survey=survey,
                            text=col_name,
                            type=dtype,
                            order=len(col_map),
                            is_required=False
                        )
                        options = {}
                        if dtype == 'single':
                            for val in sample.unique():
                                if pd.notna(val):
                                    opt = AnswerOption.objects.create(question=question, text=str(val))
                                    options[str(val)] = opt.id
                        elif dtype == 'multi':
                            unique_opts = set()
                            for val in sample:
                                if pd.notna(val):
                                    for opt in str(val).split(','):
                                        opt_clean = opt.strip()
                                        if opt_clean:
                                            unique_opts.add(opt_clean)
                            for opt_val in unique_opts:
                                opt = AnswerOption.objects.create(question=question, text=opt_val)
                                options[opt_val] = opt.id
                        col_map[col] = {
                            'question': question,
                            'dtype': dtype,
                            'options': options
                        }
                    # Only keep columns that are mapped and present in DataFrame
                    import_cols = [c for c in df.columns if c in col_map]
                    import_df = df[import_cols].fillna('') if import_cols else df
                    s_created, a_created = bulk_import_responses_postgres(survey, import_df, col_map)
                    total_surveys_created += s_created
                    total_answers_created += a_created
            except Exception as e:
                logger.exception(f"Error importing file '{getattr(file, 'name', str(file))}': {e}\n{traceback.format_exc()}")
                all_errors.append(f"Error in file '{getattr(file, 'name', str(file))}': {str(e)}")

        if total_surveys_created > 0:
            return JsonResponse({'success': True, 'surveys_created': total_surveys_created, 'answers_created': total_answers_created, 'all_errors': all_errors})
        else:
            return JsonResponse({'success': False, 'error': 'No surveys imported.', 'all_errors': all_errors}, status=400)

    # Si GET, renderizar formulario de importación
    from django.shortcuts import render
    return render(request, 'surveys/import_multiple.html')

class RespondViews:
    @staticmethod
    def respond_survey_view(request, pk=None):
        from django.shortcuts import get_object_or_404, redirect, render
        from django.contrib import messages
        from django.db import transaction
        from .models import Survey, SurveyResponse, Question, AnswerOption, QuestionResponse
        from core.utils.helpers import PermissionHelper
        from core.validators import ResponseValidator
        import logging
        logger = logging.getLogger("surveys")
        survey = get_object_or_404(Survey.objects.prefetch_related('questions__options'), pk=pk)
        # Validar que la encuesta esté activa
        if not PermissionHelper.verify_encuesta_is_active(survey):
            messages.warning(request, "Esta encuesta no está activa actualmente")
            return redirect('surveys:thanks')

        form_errors = []
        if request.method == 'POST':
            try:
                with transaction.atomic():
                    user_obj = request.user if request.user.is_authenticated else None
                    survey_response = SurveyResponse.objects.create(
                        survey=survey,
                        user=user_obj,
                        is_anonymous=(user_obj is None)
                    )
                    questions_cached = list(survey.questions.prefetch_related('options').all())
                    all_option_ids = []
                    for q in questions_cached:
                        field = f'pregunta_{q.id}'
                        if q.type == 'multi':
                            opts = request.POST.getlist(field)
                            all_option_ids.extend(opts)
                        elif q.type == 'single':
                            val = request.POST.get(field)
                            if val:
                                all_option_ids.append(val)
                    options_map = {str(op.id): op for op in AnswerOption.objects.filter(id__in=all_option_ids)}
                    for q in questions_cached:
                        field = f'pregunta_{q.id}'
                        if q.type == 'multi':
                            opts = request.POST.getlist(field)
                            txts = [options_map[o].text for o in opts if o in options_map]
                            if txts:
                                QuestionResponse.objects.create(
                                    survey_response=survey_response,
                                    question=q,
                                    text_value=",".join(txts)
                                )
                        else:
                            val = request.POST.get(field)
                            if val:
                                if q.type in ['number', 'scale']:
                                    try:
                                        if q.type == 'scale':
                                            validated_value = ResponseValidator.validate_scale_response(val)
                                        else:
                                            validated_value = ResponseValidator.validate_numeric_response(val)
                                        QuestionResponse.objects.create(
                                            survey_response=survey_response,
                                            question=q,
                                            numeric_value=int(validated_value)
                                        )
                                    except Exception as e:
                                        logger.warning(f"Respuesta numérica inválida para pregunta {q.id}: {e}")
                                elif q.type == 'single':
                                    option_obj = options_map.get(val)
                                    if option_obj:
                                        QuestionResponse.objects.create(
                                            survey_response=survey_response,
                                            question=q,
                                            selected_option=option_obj
                                        )
                                elif q.type == 'text':
                                    try:
                                        validated_text = ResponseValidator.validate_text_response(val)
                                        if validated_text:
                                            QuestionResponse.objects.create(
                                                survey_response=survey_response,
                                                question=q,
                                                text_value=validated_text
                                            )
                                    except Exception as e:
                                        logger.warning(f"Respuesta de texto inválida para pregunta {q.id}: {e}")
                    logger.info(f"Respuesta registrada exitosamente para encuesta {survey.id}")
                    return redirect('surveys:thanks')
            except Exception as e:
                logger.exception(f"Error inesperado al guardar respuesta de encuesta {pk}: {e}")
                form_errors.append("Ocurrió un error al guardar su respuesta. Por favor intente nuevamente.")
        return render(request, 'surveys/fill.html', {'survey': survey, 'form_errors': form_errors})

class ReportViews:
    @staticmethod
    def survey_results_view(request, pk=None):
        from django.shortcuts import get_object_or_404, render
        from django.http import HttpResponseBadRequest, HttpResponseForbidden
        from .models import Survey, SurveyResponse, Question
        from core.services.survey_analysis import SurveyAnalysisService
        from core.utils.helpers import DateFilterHelper, PermissionHelper, ResponseDataBuilder
        import json
        import logging
        logger = logging.getLogger("surveys")
        if pk is None:
            return HttpResponseBadRequest("Survey ID is required.")
        survey = get_object_or_404(Survey, pk=pk)
        # Permission check
        try:
            PermissionHelper.verify_encuesta_access(survey, request.user)
        except Exception:
            return HttpResponseForbidden("You do not have permission to view these results.")

        # Date/segment filters
        start = request.GET.get('start')
        end = request.GET.get('end')
        filter_col = request.GET.get('segment_col')
        filter_val = request.GET.get('segment_val')
        # Demographic filter coming from the enhanced UI. Can be a code (e.g. 'age_25_34', 'gender_male')
        # or a custom free-text value (user-specified). We prioritise segment_demo when present.
        segment_demo = request.GET.get('segment_demo')

        responses_qs = SurveyResponse.objects.filter(survey=survey)
        # Robust date filtering with error handling
        try:
            responses_qs, filter_start = DateFilterHelper.apply_filters(responses_qs, start=start, end=end)
            filter_end = end
        except Exception as e:
            logger.warning(f"Date filter error: {e}")
            filter_start = None
            filter_end = None

        # Segment by question/option/text (normalize and robust)
        # If a demographic filter is provided, try to apply it first (maps to question responses).
        if filter_col and segment_demo:
            norm_col = filter_col.strip().lower()
            q = None
            for question in survey.questions.all():
                if question.text.strip().lower() == norm_col:
                    q = question
                    break
            if q:
                try:
                    demo = segment_demo.strip()
                    # Age ranges mapping (example: age_18_24 -> numeric range or option text)
                    if demo.startswith('age_'):
                        # parse ranges like age_18_24, age_65_plus
                        if q.type in ('scale', 'number'):
                            parts = demo.split('_')
                            if len(parts) >= 3 and parts[2].isdigit():
                                low = int(parts[1])
                                high = int(parts[2])
                                responses_qs = responses_qs.filter(question_responses__question=q, question_responses__numeric_value__gte=low, question_responses__numeric_value__lte=high)
                            elif parts[-1] == 'plus' or parts[-1] == 'plus':
                                low = int(parts[1])
                                responses_qs = responses_qs.filter(question_responses__question=q, question_responses__numeric_value__gte=low)
                        else:
                            # treat as option text match (e.g. '18-24', '65+')
                            responses_qs = responses_qs.filter(question_responses__question=q).filter(
                                Q(question_responses__selected_option__text__icontains=demo) | Q(question_responses__text_value__icontains=demo)
                            )
                    elif demo.startswith('gender_'):
                        # gender_male / gender_female / gender_other
                        gender_map = {
                            'gender_male': ['hombre', 'male', 'm'],
                            'gender_female': ['mujer', 'female', 'f'],
                            'gender_other': ['otro', 'other']
                        }
                        opts = gender_map.get(demo, [demo])
                        q_filters = Q()
                        for o in opts:
                            q_filters |= Q(question_responses__selected_option__text__icontains=o) | Q(question_responses__text_value__icontains=o)
                        responses_qs = responses_qs.filter(question_responses__question=q).filter(q_filters)
                    else:
                        # Generic demographic string: try matching selected_option or text/numeric value
                        try:
                            # if the demo looks numeric, try numeric filter
                            num = float(demo)
                            responses_qs = responses_qs.filter(question_responses__question=q, question_responses__numeric_value=num)
                        except Exception:
                            # fallback to text matching
                            responses_qs = responses_qs.filter(question_responses__question=q).filter(
                                Q(question_responses__selected_option__text__icontains=demo) | Q(question_responses__text_value__icontains=demo)
                            )
                except Exception as e:
                    logger.warning(f"Demographic segmentation error: {e}")
            else:
                logger.warning(f"Segmentation question not found for demographic filter: {filter_col}")
        elif filter_col and filter_val:
            # Normalize question text for matching
            norm_col = filter_col.strip().lower()
            q = None
            for question in survey.questions.all():
                if question.text.strip().lower() == norm_col:
                    q = question
                    break
            if q:
                try:
                    if q.type == 'text':
                        responses_qs = responses_qs.filter(question_responses__question=q, question_responses__text_value__icontains=filter_val)
                    elif q.type == 'single':
                        responses_qs = responses_qs.filter(question_responses__question=q, question_responses__selected_option__text__iexact=filter_val)
                    elif q.type in ('scale', 'number'):
                        try:
                            num_val = float(filter_val)
                            responses_qs = responses_qs.filter(question_responses__question=q, question_responses__numeric_value=num_val)
                        except Exception as e:
                            logger.warning(f"Segmentation numeric parse error: {e}")
                    elif q.type == 'multi':
                        responses_qs = responses_qs.filter(question_responses__question=q, question_responses__selected_option__text__icontains=filter_val)
                except Exception as e:
                    logger.warning(f"Segmentation filter error: {e}")
            else:
                logger.warning(f"Segmentation question not found for: {filter_col}")

        responses_qs = responses_qs.distinct()
        total_respuestas = responses_qs.count()

        # Analytics
        analysis_result = SurveyAnalysisService.get_analysis_data(survey, responses_qs, include_charts=True)
        analysis_data = analysis_result.get('analysis_data', [])
        nps_data = analysis_result.get('nps_data', {})
        heatmap_image = analysis_result.get('heatmap_image')
        metrics = {
            'promedio_satisfaccion': round(analysis_result.get('kpi_prom_satisfaccion', 0), 2)
        }
        nps_score = nps_data.get('score', None)

        # Top insights (first 3 with insight)
        top_insights = [q for q in analysis_data if q.get('insight')] if analysis_data else []
        top_insights = top_insights[:3]

        # Preguntas para filtro segmentado (incluye metadata demográfica)
        preguntas_filtro = list(survey.questions.values('id', 'text', 'type', 'is_demographic', 'demographic_type'))

        # Trend data (daily counts)
        trend_labels, trend_data = ResponseDataBuilder.get_daily_counts(responses_qs, days=14)

        context = {
            'survey': survey,
            'total_respuestas': total_respuestas,
            'nps_data': nps_data,
            'nps_score': nps_score,
            'metrics': metrics,
            'analysis_data': analysis_data,
            'analysis_data_json': json.dumps(analysis_data, ensure_ascii=False, default=str),
            'trend_data': json.dumps({'labels': trend_labels, 'data': trend_data}, ensure_ascii=False),
            'top_insights': top_insights,
            'preguntas_filtro': preguntas_filtro,
            'filter_start': filter_start,
            'filter_end': filter_end,
            'filter_col': filter_col,
            'filter_val': filter_val,
            'heatmap_image': heatmap_image,
        }
        return render(request, 'surveys/results.html', context)
        @staticmethod
        def debug_analysis_view(request, pk=None):
            from django.shortcuts import get_object_or_404
            from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
            from core.services.survey_analysis import SurveyAnalysisService

            if pk is None:
                return HttpResponseBadRequest("Survey ID is required.")

            survey = get_object_or_404(Survey.objects.prefetch_related('questions__options'), pk=pk)
            try:
                PermissionHelper.verify_encuesta_access(survey, request.user)
            except Exception:
                return HttpResponseForbidden("You do not have permission to view these results.")

            respuestas_qs = SurveyResponse.objects.filter(survey=survey)
            analysis = SurveyAnalysisService.get_analysis_data(survey, respuestas_qs, include_charts=True)

            summary = []
            for q in analysis.get('analysis_data', []):
                summary.append({
                    'id': q.get('id'),
                    'text': q.get('text'),
                    'type': q.get('type'),
                    'chart_data_len': len(q.get('chart_data', {}).get('data', [])) if q.get('chart_data') else 0,
                    'has_chart_image': bool(q.get('chart_image')),
                })

            return JsonResponse({'survey_id': survey.id, 'summary': summary})
    @staticmethod
    def export_survey_csv_view(request, pk=None):
        pass
    @staticmethod
    @staticmethod
    def survey_thanks_view(request):
        from django.shortcuts import render
        return render(request, 'surveys/thanks.html')
    @staticmethod
    def cambiar_estado_encuesta(request, pk=None):
        pass

import_views = ImportViews
report_views = ReportViews
respond_views = RespondViews
# surveys/views.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, CreateView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib import messages
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from django.db import transaction, connection
from django_ratelimit.decorators import ratelimit
import json
import pandas as pd
import logging
from datetime import datetime

from .models import Survey, Question, AnswerOption, SurveyResponse, QuestionResponse
from .signals import DisableSignals
from surveys.utils.bulk_import import bulk_import_responses_postgres
from core.validators import CSVImportValidator, ResponseValidator
from core.mixins import OwnerRequiredMixin, EncuestaQuerysetMixin
from core.utils.helpers import PermissionHelper
from core.utils.logging_utils import (
    StructuredLogger,
    log_performance,
    log_user_action,
    log_data_change,
    log_security_event
)

# Configurar logger
logger = StructuredLogger('surveys')


# ============================================================
# VISTAS CRUD (Limpias, la caché se maneja por señales)
# ============================================================

class EncuestaListView(LoginRequiredMixin, EncuestaQuerysetMixin, ListView):
    """Vista lista de encuestas del usuario actual."""
    model = Survey
    template_name = 'surveys/list.html'
    context_object_name = 'surveys'


class EncuestaDetailView(LoginRequiredMixin, OwnerRequiredMixin, DetailView):
    """Vista detalle de encuesta (solo creador)."""
    model = Survey
    template_name = 'surveys/detail.html'
    context_object_name = 'survey'


class EncuestaCreateView(LoginRequiredMixin, CreateView):
    """Vista para crear nueva encuesta."""
    model = Survey
    template_name = 'surveys/survey_create.html'
    fields = ['title', 'description', 'status', 'category']
    success_url = reverse_lazy('surveys:list')

    def post(self, request, *args, **kwargs):
        # Manejo de creación vía AJAX (JSON)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
                survey = Survey.objects.create(
                    author=request.user,
                    title=data['surveyInfo'].get('title', data['surveyInfo'].get('titulo', '')),
                    description=data['surveyInfo'].get('description', data['surveyInfo'].get('descripcion', '')),
                    category=data['surveyInfo'].get('category', data['surveyInfo'].get('categoria', 'General')),
                    status='draft'
                )

                for i, q in enumerate(data['questions']):
                    question_type = {'text': 'text', 'number': 'number', 'scale': 'scale', 'single': 'single',
                            'multi': 'multi'}.get(q.get('type', q.get('tipo')), 'text')
                    question = Question.objects.create(survey=survey, text=q.get('text', q.get('titulo', '')), type=question_type, order=i,
                                                is_required=q.get('required', False))
                    if q.get('options', q.get('opciones')):
                        for opt in q.get('options', q.get('opciones', [])):
                            AnswerOption.objects.create(question=question, text=opt)

                log_user_action(
                    'create_survey',
                    success=True,
                    user_id=request.user.id,
                    survey_title=survey.title,
                    category=survey.category
                )

                return JsonResponse(
                    {'success': True, 'redirect_url': str(reverse_lazy('surveys:detail', kwargs={'pk': survey.pk}))})
            except Exception as e:
                logger.exception(f"Error al crear encuesta vía AJAX: {e}")
                return JsonResponse({'error': str(e)}, status=500)
        
        # Si no es AJAX, usar el flujo normal del formulario
        return super().post(request, *args, **kwargs)
    
    def form_valid(self, form):
        """Asigna el creador antes de guardar."""
        form.instance.author = self.request.user
        
        # Log data change
        log_user_action(
            'create_survey',
            success=True,
            user_id=self.request.user.id,
            survey_title=form.instance.title,
            category=form.instance.category
        )
        
        return super().form_valid(form)


class EncuestaUpdateView(LoginRequiredMixin, OwnerRequiredMixin, UpdateView):
    """Vista para actualizar encuesta (solo creador)."""
    model = Survey
    fields = ['title', 'description', 'status']
    template_name = 'surveys/form.html'
    success_url = reverse_lazy('surveys:list')


class EncuestaDeleteView(LoginRequiredMixin, OwnerRequiredMixin, DeleteView):
    """Vista para eliminar encuesta (solo creador)."""
    model = Survey
    template_name = 'surveys/confirm_delete.html'
    success_url = reverse_lazy('surveys:list')
    
    def post(self, request, *args, **kwargs):
        """Sobrescribe POST para usar SQL crudo en vez de ORM delete()."""
        return self.delete(request, *args, **kwargs)
    
    def delete(self, request, *args, **kwargs):
        """Eliminación ultra-rápida usando SQL crudo (bypassing ORM)."""
        from django.core.cache import cache
        from surveys.signals import disable_signals, enable_signals
        from django.db import connection
        
        # CRÍTICO: deshabilitar signals ANTES de get_object()
        disable_signals()
        
        survey = self.get_object()
        survey_id = survey.id
        author_id = survey.author.id if survey.author else None
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # SQL crudo con parámetros (seguro contra SQL injection)
                    # Orden correcto de dependencias para evitar FK errors
                    
                    # 1. QuestionResponse (tabla más pesada)
                    cursor.execute("""
                        DELETE FROM surveys_questionresponse 
                        WHERE survey_response_id IN (
                            SELECT id FROM surveys_surveyresponse WHERE survey_id = %s
                        )
                    """, [survey_id])
                    
                    # 2. SurveyResponse
                    cursor.execute("""
                        DELETE FROM surveys_surveyresponse WHERE survey_id = %s
                    """, [survey_id])
                    
                    # 3. AnswerOption
                    cursor.execute("""
                        DELETE FROM surveys_answeroption 
                        WHERE question_id IN (
                            SELECT id FROM surveys_question WHERE survey_id = %s
                        )
                    """, [survey_id])
                    
                    # 4. Question
                    cursor.execute("""
                        DELETE FROM surveys_question WHERE survey_id = %s
                    """, [survey_id])
                    
                    # 5. Survey (raíz)
                    cursor.execute("""
                        DELETE FROM surveys_survey WHERE id = %s
                    """, [survey_id])
                    
        except Exception as e:
            logger.error(f"Error eliminando encuesta {survey_id}: {e}")
            messages.error(request, "Error al eliminar la encuesta.")
            return redirect(self.success_url)
        finally:
            enable_signals()
        
        # Invalidar caché una sola vez
        if author_id:
            cache.delete(f"dashboard_data_user_{author_id}")
            try:
                cache.delete_pattern(f"survey_*{survey_id}*")
            except:
                pass
        
        messages.success(request, 'Encuesta eliminada correctamente.')
        return redirect(self.success_url)






@login_required
@ratelimit(key='user', rate='10/h', method='GET', block=True)
def survey_thanks_view(request):
    return render(request, 'surveys/thanks.html')
