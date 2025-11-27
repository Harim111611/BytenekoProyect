# surveys/apps.py
from django.apps import AppConfig

class SurveysConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'surveys'

    def ready(self):
        # Importar señales cuando la app esté lista
        import surveys.signals