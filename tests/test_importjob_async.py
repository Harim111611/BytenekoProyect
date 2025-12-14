import pytest
import os
import django
import tempfile
import shutil
from django.contrib.auth.models import User
from surveys.models import ImportJob, Survey
from surveys.tasks import process_survey_import
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

pytestmark = pytest.mark.django_db

CSV_CONTENT = """col1,col2\n1,2\n3,4\n5,6\n"""

@pytest.fixture
def test_user(db):
    return User.objects.create_user(username="testuser", password="testpass")

@pytest.fixture
def temp_csv_file():
    fd, path = tempfile.mkstemp(suffix='.csv')
    with os.fdopen(fd, 'w') as tmp:
        tmp.write(CSV_CONTENT)
    yield path
    os.remove(path)

@pytest.fixture
def client_logged(test_user):
    client = Client()
    client.force_login(test_user)
    return client

def test_importjob_creation_and_task_success(test_user, temp_csv_file):
    job = ImportJob.objects.create(user=test_user, csv_file=temp_csv_file, status='pending')
    result = process_survey_import(job.id)
    job.refresh_from_db()
    assert job.status == 'completed'
    assert job.survey is not None
    assert job.total_rows > 0
    assert result['success'] is True

def test_importjob_task_failure(test_user):
    # Archivo inexistente debe fallar
    job = ImportJob.objects.create(user=test_user, csv_file='no_existe.csv', status='pending')
    result = process_survey_import(job.id)
    job.refresh_from_db()
    assert job.status == 'failed'
    assert job.error_message
    assert result['success'] is False

def test_chunk_processing(monkeypatch, test_user):
    # Simular CSV grande
    rows = 2500
    csv_content = 'a,b\n' + '\n'.join(f'{i},{i+1}' for i in range(rows))
    fd, path = tempfile.mkstemp(suffix='.csv')
    with os.fdopen(fd, 'w') as tmp:
        tmp.write(csv_content)
    job = ImportJob.objects.create(user=test_user, csv_file=path, status='pending')
    processed_chunks = []
    orig_read_csv = pd.read_csv
    def fake_read_csv(*args, **kwargs):
        chunksize = kwargs.get('chunksize')
        assert chunksize == 1000  # Debe usar chunksize
        for i in range(0, rows, chunksize):
            df = pd.DataFrame({'a': range(i, min(i+chunksize, rows)), 'b': range(i+1, min(i+chunksize, rows)+1)})
            processed_chunks.append(len(df))
            yield df
    monkeypatch.setattr(pd, 'read_csv', fake_read_csv)
    process_survey_import(job.id)
    assert processed_chunks == [1000, 1000, 500]
    os.remove(path)

def test_import_survey_csv_async_view(client_logged, test_user, temp_csv_file):
    with open(temp_csv_file, 'rb') as f:
        upload = SimpleUploadedFile('test.csv', f.read(), content_type='text/csv')
    response = client_logged.post(reverse('surveys:import_survey_csv_async'), {'csv_file': upload})
    assert response.status_code == 200
    data = response.json()
    assert 'job_id' in data
    job = ImportJob.objects.get(id=data['job_id'])
    assert job.user == test_user
    assert job.status == 'pending'

def test_import_job_status_endpoint(client_logged, test_user, temp_csv_file):
    job = ImportJob.objects.create(user=test_user, csv_file=temp_csv_file, status='processing', processed_rows=10, total_rows=100)
    url = reverse('surveys:import_job_status', args=[job.id])
    response = client_logged.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'processing'
    assert data['processed_rows'] == 10
    assert data['total_rows'] == 100
    assert data['error_message'] is None

def test_import_job_status_endpoint_failed(client_logged, test_user, temp_csv_file):
    job = ImportJob.objects.create(user=test_user, csv_file=temp_csv_file, status='failed', error_message='Error de prueba')
    url = reverse('surveys:import_job_status', args=[job.id])
    response = client_logged.get(url)
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'failed'
    assert data['error_message'] == 'Error de prueba'
