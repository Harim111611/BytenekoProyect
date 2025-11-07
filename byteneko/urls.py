# byteneko/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),

    # Auth / dashboard (lo que ya usabas)
    path("accounts/", include("accounts.urls")),
    path("", include("accounts.urls_home")),

    # Surveys (nuevo flujo en 3 pasos)
    path("surveys/", include(("surveys.urls", "surveys"), namespace="surveys")),
]
