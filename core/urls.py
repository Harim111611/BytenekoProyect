# core/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("results/", views.dashboard_results_view, name="dashboard_results"),
    path("results/pdf/", views.global_results_pdf_view, name="global_results_pdf"),
    path("reports/", views.reports_page_view, name="reports"),
    path("reports/powerpoint/", views.report_powerpoint_view, name="report_pptx"),
    path('report/pdf/', views.report_pdf_view, name='report_pdf'),
    # --- NEW ROUTE FOR PREVIEW ---
    path("reports/preview/<int:pk>/", views.report_preview_ajax, name="report_preview"),
]