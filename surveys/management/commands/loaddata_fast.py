"""
Custom loaddata command that disables signals for faster bulk imports.
"""
from django.core.management.commands.loaddata import Command as LoadDataCommand
from surveys.signals import disable_signals, enable_signals
import logging

logger = logging.getLogger(__name__)


class Command(LoadDataCommand):
    """
    Custom loaddata command that disables survey signals during import.
    
    Usage:
        python manage.py loaddata_fast data.json
    """
    
    help = 'Import fixtures with signals disabled for maximum performance'
    
    def handle(self, *args, **options):
        """Execute loaddata with signals disabled."""
        logger.info("Disabling signals for fast bulk import...")
        disable_signals()
        
        try:
            # Call parent loaddata command
            result = super().handle(*args, **options)
            logger.info("Data imported successfully with signals disabled")
            return result
        finally:
            enable_signals()
            logger.info("Signals re-enabled")
