"""Pytest configuration for ByteNeko project."""

import os
from unittest.mock import MagicMock

import django
import pytest
from django.conf import settings

# Avoid collecting the standalone performance script which clashes with the
# real test module of the same name under scripts/.
collect_ignore = ["test_delete_speed.py", "scripts/test_delete_speed.py"]

# Force test settings module before Django setup
os.environ['DJANGO_SETTINGS_MODULE'] = 'byteneko.settings.test'


def pytest_configure():
    """Configure Django settings for pytest."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings.test')
    os.environ['DJANGO_ENV'] = 'test'

    if not settings.configured:
        django.setup()


@pytest.fixture
def mock_chart(monkeypatch):
    """Patch chart renderers used by analysis_service so tests can assert calls."""
    from core.services import analysis_service

    mock = MagicMock()
    monkeypatch.setattr(analysis_service, "render_numeric_chart", mock, raising=False)
    monkeypatch.setattr(analysis_service, "render_horizontal_bar_chart", mock, raising=False)
    monkeypatch.setattr(analysis_service, "render_nps_chart", mock, raising=False)
    return mock


@pytest.fixture
def mock_analyzer(monkeypatch):
    """Patch text analysis to inject deterministic outputs in tests."""
    from core.services import analysis_service

    mock = MagicMock()
    monkeypatch.setattr(analysis_service.TextAnalyzer, "analyze_text_responses", mock, raising=False)
    return mock


# Enable pytest-asyncio for async tests
pytest_plugins = ("pytest_asyncio",)
