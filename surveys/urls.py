# surveys/urls.py

from django.urls import path

from .views import import_views, report_views, respond_views, question_views
from .views.crud_views import (
    SurveyListView,
    SurveyCreateView,
    SurveyDetailView,
    SurveyUpdateView,
    SurveyDeleteView,
    bulk_delete_surveys_view,
)

app_name = "surveys"

urlpatterns = [
    # CRUD básico de encuestas
    path("", SurveyListView.as_view(), name="list"),
    path("create/", SurveyCreateView.as_view(), name="create"),
    path("<int:pk>/", SurveyDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", SurveyUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", SurveyDeleteView.as_view(), name="delete"),

    # Cambiar estado de una encuesta (activar / desactivar)
    path(
        "<int:pk>/change-status/",
        report_views.change_survey_status,
        name="change_status",
    ),
    
    # Operaciones CRUD de preguntas (inline desde detail view)
    path(
        "questions/<int:pk>/update/",
        question_views.update_question_view,
        name="question_update",
    ),
    path(
        "questions/<int:pk>/delete/",
        question_views.delete_question_view,
        name="question_delete",
    ),
    path(
        "<int:survey_pk>/questions/add/",
        question_views.add_question_view,
        name="question_add",
    ),

    # Importar respuestas a una encuesta existente
    # (CSV con columnas mapeadas a preguntas ya creadas)
    path(
        "<int:pk>/import/",
        import_views.import_responses_view,
        name="import",
    ),

    # Importar nueva encuesta desde CSV (flujo normal, síncrono)
    path(
        "import-new/",
        import_views.import_survey_view,
        name="import_new",
    ),

    # Vista previa de CSV (detecta tipos de columnas, muestra muestra, etc.)
    path(
        "import-preview/",
        import_views.import_csv_preview_view,
        name="import_preview",
    ),

    # Importar múltiples encuestas en un solo request
    path(
        "import-multiple/",
        import_views.import_multiple_surveys_view,
        name="import_multiple",
    ),

    # Borrado masivo de encuestas (usado por el listado + tests)
    path(
        "bulk-delete/",
        bulk_delete_surveys_view,
        name="bulk_delete",
    ),

    # Responder encuesta pública
    path(
        "<int:pk>/respond/",
        respond_views.respond_survey_view,
        name="respond",
    ),

    # Resultados y exportación
    path(
        "<int:pk>/results/",
        report_views.survey_results_view,
        name="results",
    ),
    path(
        "<int:pk>/results/debug/",
        report_views.debug_analysis_view,
        name="results_debug",
    ),
    path(
        "<int:pk>/export/",
        report_views.export_survey_csv_view,
        name="export",
    ),

    # Pantalla de agradecimiento al terminar una encuesta
    path(
        "thanks/",
        report_views.survey_thanks_view,
        name="thanks",
    ),

    # ===============================
    #  MODO TRYHARD AWS: IMPORT ASYNC
    # ===============================

    # Endpoint para lanzar una importación asíncrona
    # - Crea un ImportJob
    # - Dispara la tarea Celery process_survey_import
    # - Devuelve JSON con job_id y estado inicial
    path(
        "import-async/",
        import_views.import_survey_csv_async,
        name="import_survey_csv_async",
    ),

    # Endpoint para consultar el estado de un ImportJob (polling desde el frontend)
    # - Devuelve: status, processed_rows, total_rows, error_message, survey_id, etc.
    path(
        "import-job/<int:job_id>/status/",
        import_views.import_job_status,
        name="import_job_status",
    ),
]
