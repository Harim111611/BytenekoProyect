"""
Middleware para desarrollo local
"""
from django.http import HttpResponsePermanentRedirect
from django.conf import settings


class ForceHTTPInDevelopment:
    """
    Middleware que redirige HTTPS a HTTP en desarrollo.
    Esto evita problemas cuando el navegador fuerza HTTPS por HSTS.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Solo en desarrollo
        if settings.DEBUG and request.scheme == 'https':
            # Redirigir HTTPS a HTTP
            http_url = request.build_absolute_uri().replace('https://', 'http://')
            return HttpResponsePermanentRedirect(http_url)
        
        response = self.get_response(request)
        return response

