import logging

class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("django.request")

    def __call__(self, request):
        client_ip = request.META.get("REMOTE_ADDR")
        method = request.method
        path = request.get_full_path()
        self.logger.info(f"[REQ] {method} {path} from {client_ip}")
        return self.get_response(request)
