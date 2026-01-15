import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import User

from core.services.survey_analysis import SurveyAnalysisService
from surveys.models import AnswerOption, Question, QuestionResponse, Survey, SurveyResponse


@pytest.mark.django_db
def test_privacy_redacts_email_text_question():
    user = User.objects.create_user(username='privacy_user', password='12345')
    survey = Survey.objects.create(
        title='Privacy Survey',
        description='Test privacy redaction',
        author=user,
        status='active',
    )

    q_email = Question.objects.create(
        survey=survey,
        text='Correo electrónico',
        type='text',
        order=1,
        is_demographic=False,
    )

    sr = SurveyResponse.objects.create(survey=survey, user=user)
    QuestionResponse.objects.create(survey_response=sr, question=q_email, text_value='test@example.com')

    res = async_to_sync(SurveyAnalysisService.get_analysis_data)(
        survey,
        SurveyResponse.objects.filter(survey=survey),
        include_charts=False,
        cache_key='test_privacy_email',
        config={'include_quotes': True, 'tone': 'FORMAL'},
    )

    item = next(x for x in res.get('analysis_data', []) if x.get('id') == q_email.id)
    assert item.get('redacted') is True
    assert item.get('insight_data', {}).get('type') == 'sensitive'
    assert item.get('top_responses') == []
    assert item.get('samples_texto') == []
    assert item.get('opciones') == []


@pytest.mark.django_db
def test_privacy_redacts_metadata_choice_question_like_carrera():
    user = User.objects.create_user(username='privacy_user2', password='12345')
    survey = Survey.objects.create(
        title='Privacy Survey 2',
        description='Test privacy redaction',
        author=user,
        status='active',
    )

    q_carrera = Question.objects.create(
        survey=survey,
        text='Carrera',
        type='single',
        order=1,
        is_demographic=False,
    )
    opt_a = AnswerOption.objects.create(question=q_carrera, text='Ingeniería')

    sr = SurveyResponse.objects.create(survey=survey, user=user)
    QuestionResponse.objects.create(survey_response=sr, question=q_carrera, selected_option=opt_a)

    res = async_to_sync(SurveyAnalysisService.get_analysis_data)(
        survey,
        SurveyResponse.objects.filter(survey=survey),
        include_charts=False,
        cache_key='test_privacy_carrera',
    )

    item = next(x for x in res.get('analysis_data', []) if x.get('id') == q_carrera.id)
    assert item.get('redacted') is True
    assert item.get('insight_data', {}).get('type') == 'sensitive'
    assert item.get('opciones') == []
    assert item.get('chart_labels') == []
    assert item.get('chart_data') == []


@pytest.mark.django_db
def test_privacy_redacts_any_question_marked_demographic():
    user = User.objects.create_user(username='privacy_user3', password='12345')
    survey = Survey.objects.create(
        title='Privacy Survey 3',
        description='Test privacy redaction',
        author=user,
        status='active',
    )

    q_demo = Question.objects.create(
        survey=survey,
        text='Edad',
        type='number',
        order=1,
        is_demographic=True,
    )

    sr = SurveyResponse.objects.create(survey=survey, user=user)
    QuestionResponse.objects.create(survey_response=sr, question=q_demo, numeric_value=21)

    res = async_to_sync(SurveyAnalysisService.get_analysis_data)(
        survey,
        SurveyResponse.objects.filter(survey=survey),
        include_charts=False,
        cache_key='test_privacy_demographic',
    )

    item = next(x for x in res.get('analysis_data', []) if x.get('id') == q_demo.id)
    assert item.get('redacted') is True
    assert item.get('insight_data', {}).get('type') == 'sensitive'


@pytest.mark.django_db
def test_privacy_redacts_underscore_metadata_variants_nombre_huesped_reserva_id():
    user = User.objects.create_user(username='privacy_user4', password='12345')
    survey = Survey.objects.create(
        title='Privacy Survey 4',
        description='Test privacy redaction underscore variants',
        author=user,
        status='active',
    )

    q_guest = Question.objects.create(
        survey=survey,
        text='Nombre_Huesped',
        type='text',
        order=1,
        is_demographic=False,
    )
    q_res = Question.objects.create(
        survey=survey,
        text='Reserva_ID',
        type='text',
        order=2,
        is_demographic=False,
    )

    sr = SurveyResponse.objects.create(survey=survey, user=user)
    QuestionResponse.objects.create(survey_response=sr, question=q_guest, text_value='Juan Perez')
    QuestionResponse.objects.create(survey_response=sr, question=q_res, text_value='ABC12345')

    res = async_to_sync(SurveyAnalysisService.get_analysis_data)(
        survey,
        SurveyResponse.objects.filter(survey=survey),
        include_charts=False,
        cache_key='test_privacy_underscore_variants',
    )

    item_guest = next(x for x in res.get('analysis_data', []) if x.get('id') == q_guest.id)
    item_res = next(x for x in res.get('analysis_data', []) if x.get('id') == q_res.id)
    assert item_guest.get('redacted') is True
    assert item_res.get('redacted') is True


@pytest.mark.django_db
def test_privacy_redacts_camelcase_variants_nombreHuesped_reservaId():
    user = User.objects.create_user(username='privacy_user5', password='12345')
    survey = Survey.objects.create(
        title='Privacy Survey 5',
        description='Test privacy redaction camelCase variants',
        author=user,
        status='active',
    )

    q_guest = Question.objects.create(
        survey=survey,
        text='nombreHuesped',
        type='text',
        order=1,
        is_demographic=False,
    )
    q_res = Question.objects.create(
        survey=survey,
        text='reservaId',
        type='text',
        order=2,
        is_demographic=False,
    )

    sr = SurveyResponse.objects.create(survey=survey, user=user)
    QuestionResponse.objects.create(survey_response=sr, question=q_guest, text_value='Maria Lopez')
    QuestionResponse.objects.create(survey_response=sr, question=q_res, text_value='ABCD123456')

    res = async_to_sync(SurveyAnalysisService.get_analysis_data)(
        survey,
        SurveyResponse.objects.filter(survey=survey),
        include_charts=False,
        cache_key='test_privacy_camelcase_variants',
    )

    item_guest = next(x for x in res.get('analysis_data', []) if x.get('id') == q_guest.id)
    item_res = next(x for x in res.get('analysis_data', []) if x.get('id') == q_res.id)
    assert item_guest.get('redacted') is True
    assert item_res.get('redacted') is True


@pytest.mark.django_db
def test_privacy_redacts_identifier_column_by_values_even_if_label_unknown():
    user = User.objects.create_user(username='privacy_user6', password='12345')
    survey = Survey.objects.create(
        title='Privacy Survey 6',
        description='Test privacy redaction by identifier-like values',
        author=user,
        status='active',
    )

    # Label deliberadamente "neutro" para forzar detección por valores
    q_code = Question.objects.create(
        survey=survey,
        text='CodigoInterno',
        type='text',
        order=1,
        is_demographic=False,
    )

    # 4 respuestas con códigos únicos (alta unicidad)
    for i in range(4):
        sr = SurveyResponse.objects.create(survey=survey, user=user)
        QuestionResponse.objects.create(
            survey_response=sr,
            question=q_code,
            text_value=f'RSV{i}A9B7C3',
        )

    res = async_to_sync(SurveyAnalysisService.get_analysis_data)(
        survey,
        SurveyResponse.objects.filter(survey=survey),
        include_charts=False,
        cache_key='test_privacy_id_by_values',
        # Bajamos el umbral para que no se marque como insufficient_data y podamos comprobar redacted
        config={'min_samples': 1, 'min_samples_text': 1, 'min_samples_global_kpi': 1},
    )

    item = next(x for x in res.get('analysis_data', []) if x.get('id') == q_code.id)
    assert item.get('redacted') is True
