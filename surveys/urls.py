# surveys/urls.py
from django.urls import path
from . import views

app_name = 'surveys'

urlpatterns = [
    path('', views.EncuestaListView.as_view(), name='list'),
    path('crear/', views.EncuestaCreateView.as_view(), name='crear'),
    path('<int:pk>/', views.EncuestaDetailView.as_view(), name='detail'),
    path('<int:pk>/editar/', views.EncuestaUpdateView.as_view(), name='editar'),
    path('<int:pk>/borrar/', views.EncuestaDeleteView.as_view(), name='borrar'),
    path('<int:pk>/cambiar-estado/', views.cambiar_estado_encuesta, name='cambiar_estado'),

    # Importar en encuesta existente (método antiguo, lo mantenemos por si acaso)
    path('<int:pk>/importar/', views.import_responses_view, name='importar'),

    # --- NUEVA RUTA: IMPORTAR DESDE CERO ---
    path('importar-nueva/', views.import_survey_view, name='importar_nueva'),
    path('importar-preview/', views.import_csv_preview_view, name='importar_preview'),
    path('importar-multiple/', views.import_multiple_surveys_view, name='importar_multiple'),

    path('bulk-delete/', views.bulk_delete_surveys_view, name='bulk_delete'),

    path('<int:pk>/responder/', views.respond_survey_view, name='responder'),
    path('<int:pk>/resultados/', views.survey_results_view, name='resultados'),
    path('<int:pk>/exportar/', views.export_survey_csv_view, name='exportar'),
    path('gracias/', views.survey_thanks_view, name='thanks'),
]