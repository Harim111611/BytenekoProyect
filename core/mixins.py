"""
Mixins reutilizables para vistas de Django.
Evita duplicación de código y centraliza lógica común.
"""
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
import logging

from surveys.models import Survey

logger = logging.getLogger(__name__)


class OwnerRequiredMixin(UserPassesTestMixin):
    """
    Mixin que verifica que el usuario sea el creador de la encuesta.
    Usar en vistas que requieran acceso exclusivo al creador.
    """
    
    def test_func(self):
        """Verifica si el usuario es el creador de la encuesta."""
        # Para vistas basadas en clases con pk
        pk = self.kwargs.get('pk')
        if pk:
            survey = get_object_or_404(Survey, pk=pk)
            is_owner = survey.author == self.request.user
            
            if not is_owner:
                logger.warning(
                    f"Usuario {self.request.user.id} intentó acceder a encuesta {pk} sin permiso"
                )
            
            return is_owner
        return True
    
    def handle_no_permission(self):
        """Maneja el caso de usuario sin permiso."""
        raise PermissionDenied("No tiene permiso para acceder a esta encuesta")


class EncuestaQuerysetMixin:
    """
    Mixin que proporciona queryset optimizado de encuestas del usuario.
    Reduce N+1 queries con select_related/prefetch_related apropiados.
    """
    
    def get_queryset(self):
        """Retorna queryset optimizado de encuestas del usuario."""
        queryset = Survey.objects.filter(
            author=self.request.user
        ).select_related('author')
        
        # Si la vista necesita preguntas, usar prefetch
        if hasattr(self, 'prefetch_questions') and self.prefetch_questions:
            queryset = queryset.prefetch_related('questions__options')
        
        return queryset.order_by('-created_at')


class CacheMixin:
    """
    Mixin para generar claves de caché consistentes.
    Centraliza la lógica de caching.
    """
    
    def get_cache_key(self, prefix, **kwargs):
        """
        Genera una clave de caché consistente.
        
        Args:
            prefix: Prefijo identificador (ej: 'dashboard', 'analysis')
            **kwargs: Parámetros adicionales para la clave
            
        Returns:
            String con la clave de caché
        """
        user_id = self.request.user.id
        parts = [prefix, f"user_{user_id}"]
        
        for key, value in sorted(kwargs.items()):
            if value is not None:
                parts.append(f"{key}_{value}")
        
        return "_".join(parts)
    
    def get_cache_timeout(self):
        """Retorna el timeout de caché en segundos. Override si necesario."""
        return 300  # 5 minutos por defecto
