# byteneko/views.py
from django.shortcuts import render

def home_page_view(request):
    """
    Vista para la página de inicio (el index.html)
    """
    # Le decimos que renderice el 'index.html' que está en la carpeta 'shared'
    return render(request, 'shared/index.html')


def custom_404(request, exception=None):
    """Vista personalizada para error 404 (Página no encontrada)"""
    return render(request, 'errors/404.html', status=404)


def custom_500(request):
    """Vista personalizada para error 500 (Error del servidor)"""
    return render(request, 'errors/500.html', status=500)