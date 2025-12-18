from django.urls import path

# Importamos las vistas
from .views import import_views, report_views, respond_views, question_views
from .views import crud_views, template_views
from .views import checkout_views
from asgiref.sync import async_to_sync
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
    path('<str:public_id>/import/start/', async_to_sync(import_views.csv_upload_start_import), name='survey_import_start'),
    
    # 2. Crear NUEVA encuesta desde CSV (Listado) - SOLUCIONA EL ERROR NoReverseMatch
    path('import/new/preview/', import_csv_preview_view, name='import_preview'),
    path('import/new/start/', async_to_sync(import_views.csv_create_start_import), name='import_survey_csv_async'), # Mantenemos el nombre que busca el template
    # Compat: algunos templates/JS antiguos aún hacen reverse('surveys:import_async')
    path('import/new/start/', async_to_sync(import_views.csv_create_start_import), name='import_async'),
    
    # 3. Polling de Estado (Para ambos casos)
    path('task_status/<str:task_id>/', async_to_sync(import_views.get_task_status_view), name='task_status'),
    # Alias para compatibilidad con código JS antiguo si es necesario
    path('import-job/<str:task_id>/status/', async_to_sync(import_views.get_task_status_view), name='import_job_status'),

    # =================================================
    # RUTAS CRUD
    # API endpoints for survey templates
    path("templates/list/", async_to_sync(template_views.list_templates), name="template_list"),
    path("templates/create/", async_to_sync(template_views.create_template), name="template_create"),
    path("templates/<int:template_id>/delete/", async_to_sync(template_views.delete_template), name="template_delete"),
    # =================================================
    path("", SurveyListView.as_view(), name="list"),
    path("create/", SurveyCreateView.as_view(), name="create"),
    path("create_survey/", crud_views.api_create_survey_from_json, name="create_survey_api"),

    # Preguntas
    path("questions/<int:pk>/update/", async_to_sync(question_views.update_question_view), name="question_update"),
    path("questions/<int:pk>/delete/", async_to_sync(question_views.delete_question_view), name="question_delete"),
    path("<str:public_id>/questions/add/", async_to_sync(question_views.add_question_view), name="question_add"),

    # Acciones Masivas
    path("bulk-delete/", bulk_delete_surveys_view, name="bulk_delete"),
    path("delete-task/<str:task_id>/status/", crud_views.delete_task_status, name="delete_task_status"),

    # Acciones Varias
    path("thanks/", async_to_sync(report_views.survey_thanks_view), name="thanks"),
    path("<str:public_id>/change-status/", async_to_sync(report_views.change_survey_status), name="change_status"),
    
    # Responder
    path("<str:public_id>/respond/", async_to_sync(respond_views.respond_survey_view), name="respond"),
    
    # Resultados
    path("<str:public_id>/results/", async_to_sync(report_views.survey_results_view), name="results"),
    
    # =================================================
    # CHECKOUT API
    path("api/create-checkout/basic/", async_to_sync(checkout_views.create_checkout_basic), name="create_checkout_basic"),
    
    path("<str:public_id>/results/debug/", async_to_sync(report_views.debug_analysis_view), name="results_debug"),
    
    # --- CORRECCIÓN AQUÍ: Cambiado name="export_csv" a name="export" ---
    path("<str:public_id>/export/", async_to_sync(report_views.export_survey_csv_view), name="export"),
    
    path("<str:public_id>/api/crosstab/", async_to_sync(report_views.api_crosstab_view), name="api_crosstab"),
    
    path("<str:public_id>/api/save-segment/", async_to_sync(report_views.save_analysis_segment_view), name="save_segment"),
    
    # Detalle (Al final)
    path("<str:public_id>/", SurveyDetailView.as_view(), name="detail"),
    path("survey/<int:pk>/", legacy_survey_redirect_view, name="legacy_detail"),
    path("<str:public_id>/edit/", SurveyUpdateView.as_view(), name="edit"),
    path("<str:public_id>/delete/", SurveyDeleteView.as_view(), name="delete"),
    path("list-count/", crud_views.survey_list_count, name="list_count"),
    path("<str:public_id>/goal-decision/", crud_views.handle_goal_decision, name="handle_goal_decision"),
]