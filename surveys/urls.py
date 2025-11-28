# surveys/urls.py
from django.urls import path
from .views import import_views, report_views, respond_views
from .views.crud_views import EncuestaListView, EncuestaCreateView, EncuestaDetailView, EncuestaUpdateView, EncuestaDeleteView
from .views.report_views import cambiar_estado_encuesta
from .views.crud_views import bulk_delete_surveys_view
from .views.report_views import debug_analysis_view
from .views.import_views import import_csv_preview_view, import_multiple_surveys_view

app_name = 'surveys'

urlpatterns = [
    path('', EncuestaListView.as_view(), name='list'),
    path('crear/', EncuestaCreateView.as_view(), name='crear'),
    path('<int:pk>/', EncuestaDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', EncuestaUpdateView.as_view(), name='editar'),
    path('<int:pk>/borrar/', EncuestaDeleteView.as_view(), name='borrar'),
    path('<int:pk>/cambiar-estado/', cambiar_estado_encuesta, name='cambiar_estado'),

    # Importar en encuesta existente (método antiguo, lo mantenemos por si acaso)
    path('<int:pk>/importar/', import_views.import_responses_view, name='importar'),

    # --- NUEVA RUTA: IMPORTAR DESDE CERO ---
    path('importar-nueva/', import_views.import_survey_view, name='importar_nueva'),
    path('importar-preview/', import_csv_preview_view, name='importar_preview'),
    path('importar-multiple/', import_multiple_surveys_view, name='importar_multiple'),

    path('bulk-delete/', bulk_delete_surveys_view, name='bulk_delete'),

    path('<int:pk>/responder/', respond_views.respond_survey_view, name='responder'),
    path('<int:pk>/resultados/', report_views.survey_results_view, name='resultados'),
    path('<int:pk>/resultados/debug/', debug_analysis_view, name='resultados_debug'),
    path('<int:pk>/exportar/', report_views.export_survey_csv_view, name='exportar'),
    path('gracias/', report_views.survey_thanks_view, name='thanks'),
    path('<int:pk>/cambiar-estado/', report_views.cambiar_estado_encuesta, name='cambiar_estado'),
]