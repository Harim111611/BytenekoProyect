import pytest
import os
import django
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings')
django.setup()
from surveys.signals import disable_signals, enable_signals
from django.core.management import call_command

@pytest.mark.django_db
def test_import_speed():
    print("Importando datos con signals DESHABILITADOS...")
    print("=" * 60)
    # Measure time
    start = time.time()
    disable_signals()
    try:
        call_command('loaddata', 'data_export.json', verbosity=0)
    finally:
        enable_signals()
    end = time.time()
    duration = end - start
    print(f"\n✅ Importación completada en {duration:.2f} segundos")
    print(f"   (vs ~4.5s anteriormente con import_csv_fast)")
