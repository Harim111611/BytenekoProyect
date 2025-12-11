# core/urls.py
from django.urls import path
from . import views
from .views import payment_views

urlpatterns = [
    # --- Dashboard Principal ---
    path("", views.dashboard_view, name="dashboard"),
    path("results/", views.dashboard_results_view, name="dashboard_results"),
    
    # --- Reportes y Exportaciones ---
    path("reports/", views.reports_page_view, name="reports"),
    
    # Generación de documentos (PDF / PPTX)
    path("reports/powerpoint/", views.report_powerpoint_view, name="report_pptx"),
    path("reports/pdf/", views.report_pdf_view, name="report_pdf"),
    path("results/pdf/", views.global_results_pdf_view, name="global_results_pdf"),
    
    # Vista previa AJAX para el modal de reportes
    path("reports/preview/<str:public_id>/", views.report_preview_ajax, name="report_preview"),

    # --- MÓDULO DE PAGOS (STRIPE) ---
    # Crea la sesión de checkout para suscribirse a un plan
    path("api/create-checkout/<str:plan_slug>/", payment_views.create_checkout_session, name="create_checkout"),
    
    # Webhook para escuchar confirmaciones de pago de Stripe
    path("webhooks/stripe/", payment_views.stripe_webhook, name="stripe_webhook"),
]