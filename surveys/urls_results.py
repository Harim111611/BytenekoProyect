from django.urls import path
from . import views_results

app_name = "surveys_results"

urlpatterns = [
    path("results/<int:survey_id>/", views_results.results_detail, name="results-detail"),
]