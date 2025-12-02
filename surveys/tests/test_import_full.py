import io
import pytest
import pandas as pd
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from surveys.models import Survey, Question, AnswerOption, SurveyResponse, QuestionResponse, ImportJob
from surveys.views.import_views import _process_single_csv_import
from surveys.tasks import process_survey_import

@pytest.mark.django_db
def test_sync_import_full_types(client):
    User = get_user_model()
    user = User.objects.create_user(username='syncuser', password='pass')
    client.force_login(user)
    csv_content = (
        'single_col,multi_col,number_col,scale_col,text_col\n'
        'A,"X, Y",42,7,foo\n'
        'B,Y,100,10,bar\n'
        'A,X,0,0,"baz\nmultiline"\n'
    )
    csv_file = SimpleUploadedFile('test_types.csv', csv_content.encode('utf-8'), content_type='text/csv')
    survey, total_rows, _ = _process_single_csv_import(csv_file, user)
    assert Survey.objects.count() == 1
    assert survey.questions.count() == 5
    assert SurveyResponse.objects.count() == 3
    assert QuestionResponse.objects.count() == 9  # 3 single + 4 multi + 1*3 number + 1*3 scale + 1*3 text
    # Verifica tipos y opciones
    qmap = {q.text: q for q in survey.questions.all()}
    assert qmap['single_col'].type == 'single'
    assert qmap['multi_col'].type == 'multi'
    assert qmap['number_col'].type == 'number'
    assert qmap['scale_col'].type == 'scale'
    assert qmap['text_col'].type == 'text'
    # Opciones creadas
    single_opts = list(AnswerOption.objects.filter(question=qmap['single_col']))
    multi_opts = list(AnswerOption.objects.filter(question=qmap['multi_col']))
    assert set(o.text for o in single_opts) == {'A', 'B'}
    assert set(o.text for o in multi_opts) == {'X', 'Y'}
    # QuestionResponse apunta a opciones correctas
    for qr in QuestionResponse.objects.filter(question=qmap['single_col']):
        assert qr.selected_option.text in {'A', 'B'}
    for qr in QuestionResponse.objects.filter(question=qmap['multi_col']):
        assert qr.selected_option.text in {'X', 'Y'}
    # number/scale
    for qr in QuestionResponse.objects.filter(question=qmap['number_col']):
        assert qr.numeric_value is not None
    for qr in QuestionResponse.objects.filter(question=qmap['scale_col']):
        assert qr.numeric_value is not None
    # text
    for qr in QuestionResponse.objects.filter(question=qmap['text_col']):
        assert qr.text_value is not None

@pytest.mark.django_db
def test_async_import_job(monkeypatch, tmp_path):
    User = get_user_model()
    user = User.objects.create_user(username='asyncuser', password='pass')
    csv_path = tmp_path / 'async_test.csv'
    csv_content = (
        'single_col,multi_col,number_col,scale_col,text_col\n'
        'A,"X, Y",42,7,foo\n'
        'B,Y,100,10,bar\n'
        'A,X,0,0,baz\n'
    )
    csv_path.write_text(csv_content, encoding='utf-8')
    job = ImportJob.objects.create(user=user, csv_file=str(csv_path), status='pending')
    # Patch chunk_size to 2 for chunking test
    monkeypatch.setattr('surveys.tasks.chunk_size', 2, raising=False)
    result = process_survey_import.run(job.id)
    job.refresh_from_db()
    assert result['success']
    assert job.status == 'completed'
    assert job.processed_rows == 3
    assert job.total_rows == 3
    survey = job.survey
    assert SurveyResponse.objects.filter(survey=survey).count() == 3
    assert QuestionResponse.objects.filter(question__survey=survey).count() == 9

@pytest.mark.django_db
def test_chunking_and_consistency(monkeypatch, tmp_path):
    User = get_user_model()
    user = User.objects.create_user(username='chunkuser', password='pass')
    csv_path = tmp_path / 'chunk_test.csv'
    # 1201 filas, 2 columnas (single, multi)
    rows = ['single_col,multi_col']
    for i in range(1201):
        single = 'A' if i % 2 == 0 else 'B'
        multi = 'X, Y' if i % 3 == 0 else 'Y'
        rows.append(f'{single},"{multi}"')
    csv_path.write_text('\n'.join(rows), encoding='utf-8')
    job = ImportJob.objects.create(user=user, csv_file=str(csv_path), status='pending')
    monkeypatch.setattr('surveys.tasks.chunk_size', 1000, raising=False)
    result = process_survey_import.run(job.id)
    job.refresh_from_db()
    assert result['success']
    assert job.status == 'completed'
    assert job.processed_rows == 1201
    assert job.total_rows == 1201
    survey = job.survey
    assert SurveyResponse.objects.filter(survey=survey).count() == 1201
    # single: 1 por fila, multi: 1 o 2 por fila
    single_count = QuestionResponse.objects.filter(question__survey=survey, question__type='single').count()
    multi_count = QuestionResponse.objects.filter(question__survey=survey, question__type='multi').count()
    assert single_count == 1201
    # multi: cada 3 filas tiene 2 opciones, el resto 1
    expected_multi = (1201 // 3) * 2 + (1201 - (1201 // 3))
    assert multi_count == expected_multi
    # Opciones consistentes
    qmap = {q.text: q for q in survey.questions.all()}
    multi_opts = list(AnswerOption.objects.filter(question=qmap['multi_col']))
    assert set(o.text for o in multi_opts) == {'X', 'Y'}
    for qr in QuestionResponse.objects.filter(question=qmap['multi_col']):
        assert qr.selected_option.text in {'X', 'Y'}
