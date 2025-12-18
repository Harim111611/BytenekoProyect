#!/usr/bin/env python
"""Test the deletion speed for large surveys"""
import os
import django
import time
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings')
django.setup()

from surveys.utils.delete_optimizer import fast_delete_surveys
from surveys.models import Survey

# Find the large survey
survey = Survey.objects.filter(title='gran_dataset_10k.csv').first()
if survey:
    print(f"Testing deletion of survey ID={survey.id} with title='{survey.title}'")
    print(f"Survey has ~69,947 responses")
    
    # Measure time
    start = time.time()
    result = fast_delete_surveys([survey.id])
    elapsed = time.time() - start
    
    print(f"\n✅ Deletion completed in {elapsed:.2f} seconds")
    print(f"Result: {result}")
    print(f"\nDetails:")
    for key, val in result.get('details', {}).items():
        print(f"  - {key}: {val:,} records deleted")
else:
    print("Survey not found")
