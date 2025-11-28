# conftest.py
"""
Pytest configuration for ByteNeko project.
Forces the use of test settings regardless of environment variables.
"""
import os
import django
from django.conf import settings

# Force test settings module before Django setup
os.environ['DJANGO_SETTINGS_MODULE'] = 'byteneko.settings_test'

# Configure Django settings
def pytest_configure():
    """Configure Django settings for pytest."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings_test')
    os.environ['DJANGO_ENV'] = 'test'
    
    # Ensure Django is properly configured
    if not settings.configured:
        django.setup()


