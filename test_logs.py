#!/usr/bin/env python
"""
Script para probar que el logging esté funcionando correctamente
"""
import os
import sys
import logging
from pathlib import Path

# Add the project directory to the Python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Set Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings.local')

import django
django.setup()

from core.utils.logging_utils import StructuredLogger

def test_logging():
    print("🧪 Probando sistema de logging...")
    print("=" * 60)

    # Test 1: Logger estándar de Python
    logger = logging.getLogger('surveys')
    logger.info("[TEST] Logger estándar de Python funcionando")

    # Test 2: StructuredLogger personalizado
    structured_logger = StructuredLogger('surveys')
    structured_logger.info("[TEST] StructuredLogger funcionando")

    # Test 3: Simular logs de eliminación
    print("\n📋 Simulando logs de eliminación:")
    print("-" * 40)

    # Simular el inicio de eliminación
    logger.info("[DELETE] Iniciando eliminación optimizada SQL de 1 encuesta(s): [264]")
    logger.info("[DELETE] Step 1 - QuestionResponse: 10000 filas en 0.15s")
    logger.info("[DELETE] Step 2 - SurveyResponse: 1000 filas en 0.08s")
    logger.info("[DELETE] Step 3 - AnswerOption: 500 filas en 0.05s")
    logger.info("[DELETE] Step 4 - Question: 10 filas en 0.02s")
    logger.info("[DELETE] Step 5 - Survey: 1 filas en 0.01s")
    logger.info("[DELETE] ✅ Eliminación completa: 1 encuesta(s) en 0.31s")
    logger.info("[DELETE] Desglose: QR=0.15s (10000 filas), SR=0.08s (1000 filas), AO=0.05s (500 filas), Q=0.02s (10 filas), S=0.01s (1 filas)")

    print("\n✅ Si ves todos los logs arriba, el sistema funciona correctamente")
    print("✅ Si NO ves los logs, hay un problema con la configuración")

if __name__ == '__main__':
    test_logging()


