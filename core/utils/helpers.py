"""
Utilidades comunes para filtrado y procesamiento de datos.
Evita duplicación de código entre vistas.
"""
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from datetime import timedelta, datetime
import logging

from core.validators import DateFilterValidator

logger = logging.getLogger(__name__)

# Lazy import para evitar circular dependency
def get_log_security_event():
    from core.utils.logging_utils import log_security_event
    return log_security_event


class DateFilterHelper:
    """Helper para aplicar filtros de fecha a querysets."""
    
    @staticmethod
    def apply_filters(queryset, start=None, end=None, window=None, date_field='created_at'):
        """
        Aplica filtros de fecha a un queryset.
        
        Args:
            queryset: QuerySet a filtrar
            start: Fecha de inicio (string YYYY-MM-DD)
            end: Fecha de fin (string YYYY-MM-DD)
            window: Ventana en días (string o int)
            date_field: Nombre del campo de fecha a filtrar
            
        Returns:
            tuple: (queryset_filtrado, start_procesado)
            
        Raises:
            ValidationError: Si las fechas son inválidas
        """
        processed_start = start
        
        # Validar entradas
        if start:
            start_date = DateFilterValidator.validate_date_string(start, 'start_date')
            queryset = queryset.filter(**{f'{date_field}__date__gte': start_date})
            processed_start = start_date.strftime('%Y-%m-%d')
            
        elif window:
            days = DateFilterValidator.validate_window_days(window)
            # Si window es 'all', no aplicar filtro de fecha
            if days != 'all':
                start_dt = timezone.now() - timedelta(days=days)
                queryset = queryset.filter(**{f'{date_field}__gte': start_dt})
                processed_start = start_dt.strftime('%Y-%m-%d')
            # Si es 'all', processed_start queda None (sin filtro)
        
        if end:
            end_date = DateFilterValidator.validate_date_string(end, 'end_date')
            queryset = queryset.filter(**{f'{date_field}__date__lte': end_date})
        
        # Validar rango si ambos están presentes
        if start and end:
            DateFilterValidator.validate_date_range(start, end)
        
        return queryset, processed_start
    
    @staticmethod
    def build_date_range_label(start=None, end=None, window=None):
        """
        Construye una etiqueta legible para el rango de fechas.
        
        Args:
            start: Fecha de inicio
            end: Fecha de fin
            window: Ventana en días
            
        Returns:
            String con la etiqueta del rango
        """
        if window:
            return f"Últimos {window} días"
        
        parts = []
        if start:
            try:
                start_date = datetime.strptime(start, '%Y-%m-%d').date()
                parts.append(f"Desde {start_date.strftime('%d/%m/%Y')}")
            except ValueError:
                pass
        
        if end:
            try:
                end_date = datetime.strptime(end, '%Y-%m-%d').date()
                connector = " hasta " if parts else "Hasta "
                parts.append(f"{connector}{end_date.strftime('%d/%m/%Y')}")
            except ValueError:
                pass
        
        return "".join(parts) if parts else "Todo el histórico"


class ResponseDataBuilder:
    """Helper para construir estructura de datos de respuestas."""
    
    @staticmethod
    def get_daily_counts(survey_response_queryset, days=14):
        """
        Get daily counts of survey responses for charts.
        
        Args:
            survey_response_queryset: QuerySet of SurveyResponse
            days: Number of days to include
        Returns:
            tuple: (labels, data) for Chart.js
        """
        from django.db.models.functions import TruncDate
        from django.db.models import Count
        
        today = timezone.now().date()
        start_date = today - timedelta(days=days - 1)
        
        daily_data = (
            survey_response_queryset
            .filter(created_at__date__gte=start_date)
            .annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(count=Count('id'))
            .order_by('date')
        )
        
        # Crear mapa de fechas a conteos
        date_map = {item['date']: item['count'] for item in daily_data}
        
        # Generar arrays completos incluyendo días sin respuestas
        labels = []
        data = []
        curr = start_date
        
        while curr <= today:
            labels.append(curr.strftime('%d %b'))
            data.append(date_map.get(curr, 0))
            curr += timedelta(days=1)
        
        return labels, data
    
    @staticmethod
    def get_status_distribution(survey_queryset):
        """
        Get distribution of survey statuses.
        
        Args:
            survey_queryset: QuerySet of Survey
        Returns:
            list: [active, draft, closed]
        """
        from django.db.models import Count
        
        status_counts = survey_queryset.values('status').annotate(count=Count('id'))
        status_map = {s['status']: s['count'] for s in status_counts}
        
        return [
            status_map.get('active', 0),
            status_map.get('paused', 0),
            status_map.get('draft', 0),
            status_map.get('closed', 0)
        ]


class PermissionHelper:
    """Helper para validación de permisos de usuario."""
    
    @staticmethod
    def verify_survey_access(survey, user):
        """
        Verify that the user has access to the survey.
        
        Args:
            survey: Survey instance
            user: User to verify
        Raises:
            PermissionDenied: If the user does not have access
        """
        if survey.author != user:
            # Log security event
            log_security = get_log_security_event()
            log_security(
                'unauthorized_survey_access',
                severity='WARNING',
                user_id=user.id,
                survey_id=survey.id,
                survey_author_id=survey.author.id
            )
            logger.warning(
                f"User {user.id} tried to access survey {survey.id} without permission"
            )
            raise PermissionDenied("No tiene permiso para acceder a esta encuesta")
    
    @staticmethod
    def verify_survey_is_active(survey):
        """
        Verify that the survey is active.
        
        Args:
            survey: Survey instance
        Returns:
            bool: True if active
        """
        return survey.status == 'active'
