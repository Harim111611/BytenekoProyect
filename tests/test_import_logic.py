import pytest
import os
import django

from surveys.models import ImportJob, Survey
from django.contrib.auth.models import User
from surveys.tasks import process_survey_import

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings.test')
django.setup()

@pytest.mark.django_db
def test_import_logic():
    archivos = [
        'data/samples/encuesta_clima_laboral.csv',
        'data/samples/encuesta_satisfaccion_universitaria.csv',
        'data/samples/encuesta_hospital_servicios.csv',
    ]

    user = User.objects.first()

    for csv_filename in archivos:
        print(f"\n{'='*80}")
        print(f"Procesando: {csv_filename}")
        print('='*80)
        try:
            job = ImportJob.objects.create(user=user, csv_file=csv_filename, status='pending')
            result = process_survey_import(job.id)
            job.refresh_from_db()
            if result['success']:
                print(f"✓ Importación exitosa: {job.total_rows} filas, encuesta id={job.survey.id}")
            else:
                print(f"✗ Error: {job.error_message}")
        except Exception as e:
            print(f"✗ ERROR: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*80}")
    print("Prueba completada")
