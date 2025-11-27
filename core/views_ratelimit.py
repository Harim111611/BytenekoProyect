"""
Rate limiting error handler for core app.
"""

from django.shortcuts import render


def ratelimit_error(request, exception=None):
    """Vista personalizada para errores de rate limiting."""
    return render(
        request,
        'core/ratelimit_error.html',
        {
            'message': 'Has excedido el límite de solicitudes permitidas. Por favor, inténtalo más tarde.',
        },
        status=429
    )
