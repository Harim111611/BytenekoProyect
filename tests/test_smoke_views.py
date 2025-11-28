import pytest
from django.test import RequestFactory
from core import views

def test_dashboard_view_smoke():
    from django.contrib.auth.models import AnonymousUser
    rf = RequestFactory()
    request = rf.get("/dashboard/")
    request.user = AnonymousUser()
    response = views.dashboard_view(request)
    assert hasattr(response, "status_code")

def test_dashboard_results_view_importable():
    assert hasattr(views, "dashboard_results_view")

def test_global_results_pdf_view_importable():
    assert hasattr(views, "global_results_pdf_view")

def test_reports_page_view_importable():
    assert hasattr(views, "reports_page_view")

def test_report_pdf_view_importable():
    assert hasattr(views, "report_pdf_view")

def test_report_powerpoint_view_importable():
    assert hasattr(views, "report_powerpoint_view")

def test_settings_view_importable():
    assert hasattr(views, "settings_view")
