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

    # Apps
    path("dashboard/", core_views.dashboard_view, name="dashboard"),
    path("resultados/", core_views.results_dashboard_view, name="results"),
    path("reportes/", core_views.reports_page_view, name="reports"),

    # Reportes
    path(
        "reportes/powerpoint/",
        core_views.report_powerpoint_view,
        name="report_pptx",
    ),

    # --- CORRECCIÓN AQUÍ ---
    # Se ha cambiado 'report_preview_view' por 'report_preview_ajax'
    # para que coincida con el nombre de la función en core/views.py
    path(
        "reportes/preview/<int:pk>/",
        core_views.report_preview_ajax,  # <--- ESTE ES EL CAMBIO
        name="report_preview",
    ),

    path("surveys/", include("surveys.urls")),

    # Inicio
    path("", RedirectView.as_view(pattern_name="login", permanent=False), name="index"),
]