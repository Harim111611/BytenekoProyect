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

    # Importar en encuesta existente (método antiguo, lo mantenemos por si acaso)
    path('<int:pk>/importar/', views.import_responses_view, name='importar'),

    # --- NUEVA RUTA: IMPORTAR DESDE CERO ---
    path('importar-nueva/', views.import_new_survey_view, name='importar_nueva'),

    path('<int:pk>/responder/', views.responder, name='responder'),
    path('<int:pk>/resultados/', views.resultados, name='resultados'),
    path('<int:pk>/exportar/', views.export_csv, name='exportar'),
    path('gracias/', views.thanks_view, name='thanks'),
]