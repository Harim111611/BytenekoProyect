from django.urls import path

# Importamos las vistas
from . import views
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
    # RUTAS DE IMPORTACIÓN
    # =================================================
    # 1. Importar en encuesta existente (Detalle)
    path('<str:public_id>/import/start/', import_views.csv_upload_start_import, name='survey_import_start'),
    
    # 2. Crear NUEVA encuesta desde CSV (Listado)
    path('import/new/preview/', import_csv_preview_view, name='import_preview'),
    path('import/new/start/', import_views.csv_create_start_import, name='import_survey_csv_async'),
    
    # 3. Polling de Estado para IMPORTACIONES (IDs Numéricos de Base de Datos)
    # FIX: Cambiado str -> int para evitar colisiones con UUIDs de Celery
    path('import-job/<int:task_id>/status/', import_views.get_task_status_view, name='import_job_status'),
    # Polling genérico por UUID para tareas de Celery
    path('task_status/<uuid:task_id>/', views.task_status_view, name='task_status'),

    # =================================================
    # RUTAS CRUD
    # =================================================
    path("templates/list/", template_views.list_templates, name="template_list"),
    path("templates/create/", template_views.create_template, name="template_create"),
    path("templates/<int:template_id>/delete/", template_views.delete_template, name="template_delete"),
    
    path("", SurveyListView.as_view(), name="list"),
    path("create/", SurveyCreateView.as_view(), name="create"),
    path("create_survey/", crud_views.api_create_survey_from_json, name="create_survey_api"),

    # Preguntas
    path("questions/<int:pk>/update/", question_views.update_question_view, name="question_update"),
    path("questions/<int:pk>/delete/", question_views.delete_question_view, name="question_delete"),
    path("<str:public_id>/questions/add/", question_views.add_question_view, name="question_add"),

    # Acciones Masivas
    path("bulk-delete/", bulk_delete_surveys_view, name="bulk_delete"),
    
    # FIX: Ruta específica para polling de tareas de ELIMINACIÓN (UUIDs de Celery)
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
    path("<str:public_id>/export/", report_views.export_survey_csv_view, name="export"),
    path("<str:public_id>/api/crosstab/", report_views.api_crosstab_view, name="api_crosstab"),
    
    # Detalle (Al final para no opacar otras rutas)
    path("<str:public_id>/", SurveyDetailView.as_view(), name="detail"),
    path("survey/<int:pk>/", legacy_survey_redirect_view, name="legacy_detail"),
    path("<str:public_id>/edit/", SurveyUpdateView.as_view(), name="edit"),
    path("<str:public_id>/delete/", SurveyDeleteView.as_view(), name="delete"),
    path("list-count/", crud_views.survey_list_count, name="list_count"),
    path("<str:public_id>/goal-decision/", crud_views.handle_goal_decision, name="handle_goal_decision"),
    
    # Rutas para reportes asíncronos
    path('reports/pdf/create/', report_views.report_pdf_view, name='report_pdf_create'),
    path('reports/pptx/create/', report_views.report_powerpoint_view, name='report_pptx_create'),
    path('reports/status/<int:job_id>/', report_views.check_report_status, name='check_report_status'),
    path('reports/download/<int:job_id>/', report_views.download_report_file, name='download_report'),
]