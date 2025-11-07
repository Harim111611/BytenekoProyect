from django.contrib import admin
from django.urls import path, include
from django.views.generic.base import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),

    # Resultados (con namespace)
    path(
        "surveys/",
        include(("surveys.urls_results", "surveys_results"), namespace="surveys_results"),
    ),
    path("favicon.ico", RedirectView.as_view(url="/static/img/favicon.ico", permanent=False)),

    # Auth / dashboard
    path("accounts/", include("accounts.urls")),
    path("", include("accounts.urls_home")),

    # Surveys (flujo de creación en 3 pasos) — mantiene su propio namespace "surveys"
    path("surveys/", include(("surveys.urls", "surveys"), namespace="surveys")),
]
