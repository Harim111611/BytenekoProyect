import io
import pytest
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from surveys.models import Survey, Question, AnswerOption, SurveyResponse, QuestionResponse
from django.contrib.auth.models import User

@pytest.mark.django_db
def test_import_survey_happy(client):
    user = User.objects.create_user(username='testuser', password='testpass')
    client.login(username='testuser', password='testpass')
    csv_content = 'Pregunta 1,Pregunta 2\nOpción A,10\nOpción B,5\n'
    csv_file = SimpleUploadedFile('test.csv', csv_content.encode('utf-8'), content_type='text/csv')
    url = reverse('surveys:import_new')
    print(f"[DEBUG] import_new URL: {url}")
    response = client.post(url, {'csv_file': csv_file}, follow=True)
    if response.status_code != 200:
        print(f"[FAIL] Status: {response.status_code}\nContent: {response.content}")
    assert response.status_code == 200
    data = response.json()
    assert data['success']
    assert Survey.objects.count() == 1
    assert Question.objects.count() == 2
    assert SurveyResponse.objects.count() == 2
    assert QuestionResponse.objects.count() == 4

@pytest.mark.django_db
def test_import_survey_missing_column(client):
    user = User.objects.create_user(username='testuser', password='testpass')
    client.login(username='testuser', password='testpass')
    csv_content = 'SoloUnaColumna\nDato1\nDato2\n'
    csv_file = SimpleUploadedFile('test.csv', csv_content.encode('utf-8'), content_type='text/csv')
    response = client.post(reverse('surveys:import_new'), {'csv_file': csv_file}, follow=True)
    if response.status_code != 400:
        print(f"[FAIL] Status: {response.status_code}\nContent: {response.content}")
    assert response.status_code == 400
    data = response.json()
    assert not data['success']
    assert 'error' in data

@pytest.mark.django_db
def test_import_survey_too_large(client, settings):
    user = User.objects.create_user(username='testuser', password='testpass')
    client.login(username='testuser', password='testpass')
    big_content = 'Col1\n' + ('x\n' * (1024 * 1024 * 12))  # ~12MB
    csv_file = SimpleUploadedFile('big.csv', big_content.encode('utf-8'), content_type='text/csv')
    response = client.post(reverse('surveys:import_new'), {'csv_file': csv_file}, follow=True)
    if response.status_code != 400:
        print(f"[FAIL] Status: {response.status_code}\nContent: {response.content}")
    assert response.status_code == 400
    data = response.json()
    assert not data['success']
    assert 'demasiado grande' in data['error'].lower()

@pytest.mark.django_db
def test_bulk_delete_permissions(client):
    user1 = User.objects.create_user(username='user1', password='pass1')
    user2 = User.objects.create_user(username='user2', password='pass2')
    client.login(username='user1', password='pass1')
    survey = Survey.objects.create(title='S1', author=user2)
    response = client.post(reverse('surveys:bulk_delete'), {'survey_ids': [survey.id]}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert response.status_code in (403, 404)
    data = response.json()
    assert not data['success']

@pytest.mark.django_db
def test_bulk_delete_happy(client):
    user = User.objects.create_user(username='testuser', password='testpass')
    client.login(username='testuser', password='testpass')
    survey = Survey.objects.create(title='S1', author=user)
    q = Question.objects.create(survey=survey, text='Q1', type='text', order=0)
    sr = SurveyResponse.objects.create(survey=survey)
    QuestionResponse.objects.create(survey_response=sr, question=q, text_value='A')
    response = client.post(reverse('surveys:bulk_delete'), {'survey_ids': [survey.id]}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert response.status_code == 200
    data = response.json()
    assert data['success']
    assert Survey.objects.count() == 0
    assert Question.objects.count() == 0
    assert SurveyResponse.objects.count() == 0
    assert QuestionResponse.objects.count() == 0
