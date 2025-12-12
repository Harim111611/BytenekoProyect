from django.urls import path

# Importamos las vistas
from .views import import_views, report_views, respond_views, question_views
from .views import crud_views, template_views
from .views import checkout_views
from .views.crud_views import (
    SurveyListView,
    SurveyCreateView,
    SurveyDetailView,
    SurveyUpdateView,
    SurveyDeleteView,
    bulk_delete_surveys_view,
    legacy_survey_redirect_view,
)
from surveys.views_preview import import_csv_preview_view

app_name = "surveys"

urlpatterns = [
    # =================================================
    # RUTAS DE IMPORTACIÓN (NUEVAS Y CORRECTAS)
    # =================================================
    # 1. Importar en encuesta existente (Detalle)
    path('<str:public_id>/import/start/', import_views.csv_upload_start_import, name='survey_import_start'),
    
    # 2. Crear NUEVA encuesta desde CSV (Listado) - SOLUCIONA EL ERROR NoReverseMatch
    path('import/new/preview/', import_csv_preview_view, name='import_preview'),
    path('import/new/start/', import_views.csv_create_start_import, name='import_survey_csv_async'), # Mantenemos el nombre que busca el template
    
    # 3. Polling de Estado (Para ambos casos)
    path('task_status/<str:task_id>/', import_views.get_task_status_view, name='task_status'),
    # Alias para compatibilidad con código JS antiguo si es necesario
    path('import-job/<str:task_id>/status/', import_views.get_task_status_view, name='import_job_status'),

    # =================================================
    # RUTAS CRUD
    # API endpoints for survey templates
    path("templates/list/", template_views.list_templates, name="template_list"),
    path("templates/create/", template_views.create_template, name="template_create"),
    path("templates/<int:template_id>/delete/", template_views.delete_template, name="template_delete"),
    # =================================================
    path("", SurveyListView.as_view(), name="list"),
    path("create/", SurveyCreateView.as_view(), name="create"),
    path("create_survey/", crud_views.api_create_survey_from_json, name="create_survey_api"),

    # Preguntas
    path("questions/<int:pk>/update/", question_views.update_question_view, name="question_update"),
    path("questions/<int:pk>/delete/", question_views.delete_question_view, name="question_delete"),
    path("<str:public_id>/questions/add/", question_views.add_question_view, name="question_add"),

    # Acciones Masivas
    path("bulk-delete/", bulk_delete_surveys_view, name="bulk_delete"),
    path("delete-task/<str:task_id>/status/", crud_views.delete_task_status, name="delete_task_status"),

    # Acciones Varias
    path("thanks/", report_views.survey_thanks_view, name="thanks"),
    path("<str:public_id>/change-status/", report_views.change_survey_status, name="change_status"),
    
    # Responder
    path("<str:public_id>/respond/", respond_views.respond_survey_view, name="respond"),
    
    # Resultados
    path("<str:public_id>/results/", report_views.survey_results_view, name="results"),
    
    # =================================================
    # CHECKOUT API
    path("api/create-checkout/basic/", checkout_views.create_checkout_basic, name="create_checkout_basic"),
    
    path("<str:public_id>/results/debug/", report_views.debug_analysis_view, name="results_debug"),
    
    # --- CORRECCIÓN AQUÍ: Cambiado name="export_csv" a name="export" ---
    path("<str:public_id>/export/", report_views.export_survey_csv_view, name="export"),
    
    path("<str:public_id>/api/crosstab/", report_views.api_crosstab_view, name="api_crosstab"),
    
    # Detalle (Al final)
    path("<str:public_id>/", SurveyDetailView.as_view(), name="detail"),
    path("survey/<int:pk>/", legacy_survey_redirect_view, name="legacy_detail"),
    path("<str:public_id>/edit/", SurveyUpdateView.as_view(), name="edit"),
    path("<str:public_id>/delete/", SurveyDeleteView.as_view(), name="delete"),
    path("list-count/", crud_views.survey_list_count, name="list_count"),
    path("<str:public_id>/goal-decision/", crud_views.handle_goal_decision, name="handle_goal_decision"),
]