# byteneko/views.py

from django.shortcuts import render
from asgiref.sync import sync_to_async


async def home_page_view(request):
    """
    Vista para la página de inicio (el index.html)
    """
    render_async = sync_to_async(render, thread_sensitive=True)
    return await render_async(request, 'shared/index.html')



async def custom_404(request, exception=None):
    """Vista personalizada para error 404 (Página no encontrada)"""
    render_async = sync_to_async(render, thread_sensitive=True)
    return await render_async(request, 'errors/404.html', status=404)



async def custom_500(request):
    """Vista personalizada para error 500 (Error del servidor)"""
    render_async = sync_to_async(render, thread_sensitive=True)
    return await render_async(request, 'errors/500.html', status=500)