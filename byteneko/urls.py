# byteneko/urls.py
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.views.generic.base import RedirectView

from core import views as core_views
from asgiref.sync import async_to_sync
from . import views_checkout

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    # API Checkout global
    path("api/create-checkout/basic/", views_checkout.create_checkout_basic, name="create_checkout_basic"),

    # Autenticación
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="shared/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # Apps (Core)

    path("dashboard/", async_to_sync(core_views.dashboard_view), name="dashboard"),
    path("results/", async_to_sync(core_views.dashboard_results_view), name="dashboard_results"),
    path("results/pdf/", async_to_sync(core_views.global_results_pdf_view), name="global_results_pdf"),
    path("reports/", async_to_sync(core_views.reports_page_view), name="reports"),

    # --- NEW ROUTE ADDED HERE ---
    path("settings/", async_to_sync(core_views.settings_view), name="settings"),

    # Specific Reports
    path(
        "report/pdf/",
        async_to_sync(core_views.report_pdf_view),
        name="report_pdf",
    ),
    path(
        "reports/powerpoint/",
        async_to_sync(core_views.report_powerpoint_view),
        name="report_pptx",
    ),
    path(
        "reports/preview/<str:public_id>/",
        async_to_sync(core_views.report_preview_ajax),
        name="report_preview",
    ),

    # Surveys App
    path("surveys/", include("surveys.urls")),

    # Inicio (Redirección)
    path("", RedirectView.as_view(pattern_name="login", permanent=False), name="index"),
]

# Configurar handlers de error personalizados
handler404 = 'byteneko.views.custom_404'
handler500 = 'byteneko.views.custom_500'
