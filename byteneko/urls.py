# byteneko/urls.py
from django.contrib import admin
from django.urls import path, include


from django.views.generic.base import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("favicon.ico", RedirectView.as_view(url="/static/img/favicon.ico", permanent=False)),


    # Auth / dashboard (lo que ya usabas)
    path("accounts/", include("accounts.urls")),
    path("", include("accounts.urls_home")),

    # Surveys (nuevo flujo en 3 pasos)
    path("surveys/", include(("surveys.urls", "surveys"), namespace="surveys")),
]
