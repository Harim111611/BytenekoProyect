# byteneko/urls.py
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.views.generic.base import RedirectView

from core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),

    # Autenticación
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="authentication/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # Apps (Core)
    path("dashboard/", core_views.dashboard_view, name="dashboard"),
    path("resultados/", core_views.dashboard_results_view, name="dashboard_results"),
    path("resultados/pdf/", core_views.global_results_pdf_view, name="global_results_pdf"),
    path("reportes/", core_views.reports_page_view, name="reports"),

    # --- NUEVA RUTA AGREGADA AQUÍ ---
    path("configuracion/", core_views.settings_view, name="settings"),

    # Reportes Específicos
    path(
        "report/pdf/",
        core_views.report_pdf_view,
        name="report_pdf",
    ),
    path(
        "reportes/powerpoint/",
        core_views.report_powerpoint_view,
        name="report_pptx",
    ),
    path(
        "reportes/preview/<int:pk>/",
        core_views.report_preview_ajax,
        name="report_preview",
    ),

    # Surveys App
    path("surveys/", include("surveys.urls")),

    # Inicio (Redirección)
    path("", RedirectView.as_view(pattern_name="login", permanent=False), name="index"),
]
