import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings.production')
django.setup()

from django.core.management import call_command

# Export data with UTF-8 encoding
with open('data_export.json', 'w', encoding='utf-8') as f:
    call_command(
        'dumpdata',
        '--natural-foreign',
        '--natural-primary',
        '--exclude', 'contenttypes',
        '--exclude', 'auth.Permission',
        '--exclude', 'sessions',
        '--exclude', 'admin.LogEntry',
        '--indent', '2',
        stdout=f
    )

print("Data exported successfully to data_export.json")
