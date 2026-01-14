import logging
import time

class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("django.request")

    def __call__(self, request):
        # Registrar información de la solicitud
        client_ip = request.META.get("REMOTE_ADDR")
        method = request.method
        path = request.get_full_path()
        # Evitar AttributeError si request.user no existe
        user_obj = getattr(request, 'user', None)
        if user_obj and hasattr(user_obj, 'username'):
            user = user_obj.username or 'anónimo'
        else:
            user = 'anónimo'
        
        # Medir tiempo de respuesta
        start_time = time.time()
        response = self.get_response(request)
        elapsed_time = time.time() - start_time
        
        # Solo loguear requests de admin y API, saltar archivos estáticos
        if path.startswith('/admin') or path.startswith('/api') or path.startswith('/surveys'):
            status_code = response.status_code
            emoji = '✅' if 200 <= status_code < 300 else '⚠️' if 300 <= status_code < 400 else '❌'
            
            log_level = 'INFO' if 200 <= status_code < 400 else 'WARNING'
            log_method = getattr(self.logger, log_level.lower(), self.logger.info)
            
            log_method(
                f"{emoji} {method:6} {status_code} | {path:40} | {elapsed_time:.3f}s | {user} | {client_ip}"
            )
        
        return response
