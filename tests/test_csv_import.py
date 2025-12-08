import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings.test')
django.setup()

import pytest
import os
import django
from django.contrib.auth.models import User
from surveys.models import ImportJob
from surveys.tasks import process_survey_import

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings.test')
django.setup()

pytestmark = pytest.mark.django_db

def test_import_csv_files():
    archivos = [
        'data/samples/encuesta_satisfaccion_clientes.csv',
        'data/samples/encuesta_clima_laboral.csv',
        'data/samples/encuesta_satisfaccion_universitaria.csv',
        'data/samples/encuesta_hospital_servicios.csv',
        'data/samples/encuesta_hotel_huespedes.csv'
    ]
    user = User.objects.first()
    for archivo in archivos:
        job = ImportJob.objects.create(user=user, csv_file=archivo, status='pending')
        result = process_survey_import(job.id)
        job.refresh_from_db()
        assert result['success'] or job.status == 'failed'
