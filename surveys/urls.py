# surveys/urls.py
from django.urls import path
from . import views

app_name = "surveys"

urlpatterns = [
    # Lista de encuestas
    path("", views.EncuestaListView.as_view(), name="list"),

    # Crear encuesta (asistente JS)
    path("crear/", views.EncuestaCreateView.as_view(), name="crear"),

    # Detalle de una encuesta
    path("<int:pk>/", views.EncuestaDetailView.as_view(), name="detail"),

    # Editar metadatos de la encuesta (título, descripción, etc.)
    path("<int:pk>/editar/", views.EncuestaUpdateView.as_view(), name="editar"),

    # Eliminar encuesta (coincide con /surveys/${pk}/borrar/ del JS)
    path("<int:pk>/borrar/", views.EncuestaDeleteView.as_view(), name="borrar"),

    # Importar respuestas desde CSV
    path("<int:pk>/importar/", views.import_responses_view, name="importar"),

    # Responder encuesta (vista pública/llena el formulario)
    path("<int:pk>/responder/", views.responder, name="responder"),

    # Dashboard de resultados de la encuesta
    path("<int:pk>/resultados/", views.resultados, name="resultados"),

    # Exportar respuestas a CSV
    path("<int:pk>/exportar/", views.export_csv, name="exportar"),

    # Página de "gracias" posterior a responder
    path("gracias/", views.thanks_view, name="gracias"),
]
