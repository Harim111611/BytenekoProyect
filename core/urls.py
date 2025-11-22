# core/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("resultados/", views.results_dashboard_view, name="results"),
    path("reportes/", views.reports_page_view, name="reports"),
    path("reportes/powerpoint/", views.report_powerpoint_view, name="report_pptx"),
    path('report/pdf/', views.report_pdf_view, name='report_pdf'),
    # --- ¡NUEVA RUTA PARA VISTA PREVIA! ---
    path("reportes/preview/<int:pk>/", views.report_preview_ajax, name="report_preview"),
]