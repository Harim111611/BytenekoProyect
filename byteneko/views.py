# byteneko/views.py
from django.shortcuts import render

def home_page_view(request):
    """
    Vista para la página de inicio (el index.html)
    """
    # Le decimos que renderice el 'index.html' que está en la carpeta 'pages'
    return render(request, 'pages/index.html')