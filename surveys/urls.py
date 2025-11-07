# surveys/urls.py
from django.urls import path
from .views import CreateStep1View, CreateStep2View, Step3Review  # <-- nombres reales

app_name = "surveys"

urlpatterns = [
    path("create/step-1/", CreateStep1View.as_view(), name="create_step_1"),
    path("create/step-2/", CreateStep2View.as_view(), name="create_step_2"),
    path("create/step-3/", Step3Review.as_view(),   name="create_step_3"),
]
