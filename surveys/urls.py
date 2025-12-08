# surveys/urls.py

from django.urls import path

from .views import import_views, report_views, respond_views, question_views
from .views import crud_views
from .views.crud_views import (
    SurveyListView,
    SurveyCreateView,
    SurveyDetailView,
    SurveyUpdateView,
    SurveyDeleteView,
    bulk_delete_surveys_view,
    legacy_survey_redirect_view,
)

app_name = "surveys"

urlpatterns = [
    # CRUD básico de encuestas
    path("", SurveyListView.as_view(), name="list"),
    path("create/", SurveyCreateView.as_view(), name="create"),

    # Operaciones CRUD de preguntas (inline desde detail view)
    path("questions/<int:pk>/update/", question_views.update_question_view, name="question_update"),
    path("questions/<int:pk>/delete/", question_views.delete_question_view, name="question_delete"),

    # Vista previa de CSV
    path("import-preview/", import_views.import_csv_preview_view, name="import_preview"),

    # Borrado masivo
    path("bulk-delete/", bulk_delete_surveys_view, name="bulk_delete"),

    # Pantalla de agradecimiento
    path("thanks/", report_views.survey_thanks_view, name="thanks"),

    # MODO TRYHARD AWS: IMPORT ASYNC
    path("import-async/", import_views.import_survey_csv_async, name="import_survey_csv_async"),
    path("import-job/<int:job_id>/status/", import_views.import_job_status, name="import_job_status"),
    path("delete-task/<str:task_id>/status/", crud_views.delete_task_status, name="delete_task_status"),

    # Rutas legadas
    path("<int:pk>/<path:legacy_path>/", legacy_survey_redirect_view, name="legacy_survey_with_path"),
    path("<int:pk>/", legacy_survey_redirect_view, name="legacy_survey"),

    # Rutas modernas con identificador público
    path("<str:public_id>/", SurveyDetailView.as_view(), name="detail"),
    path("<str:public_id>/edit/", SurveyUpdateView.as_view(), name="edit"),
    path("<str:public_id>/delete/", SurveyDeleteView.as_view(), name="delete"),
    path("<str:public_id>/change-status/", report_views.change_survey_status, name="change_status"),
    path("<str:public_id>/questions/add/", question_views.add_question_view, name="question_add"),
    path("<str:public_id>/import/", import_views.import_responses_view, name="import"),
    path("<str:public_id>/respond/", respond_views.respond_survey_view, name="respond"),
    path("<str:public_id>/results/", report_views.survey_results_view, name="results"),
    path("<str:public_id>/results/debug/", report_views.debug_analysis_view, name="results_debug"),
    path("<str:public_id>/export/", report_views.export_survey_csv_view, name="export"),
    path("list-count/", crud_views.survey_list_count, name="list_count"),
    
    # NUEVA RUTA PARA DECISIÓN DE META
    path("<str:public_id>/goal-decision/", crud_views.handle_goal_decision, name="handle_goal_decision"),
]