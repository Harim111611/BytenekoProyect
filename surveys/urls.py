# surveys/urls.py
from django.urls import path
from . import views

app_name = "surveys"

urlpatterns = [
    path("create/step-1/", views.CreateStep1View.as_view(), name="create_step_1"),
    path("create/step-2/", views.CreateStep2View.as_view(), name="create_step_2"),
    path("create/step-3/", views.Step3Review.as_view(),    name="create_step_3"),
]
