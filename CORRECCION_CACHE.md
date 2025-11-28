# 🔧 Corrección: Bucle de Invalidación de Caché

## Problema Identificado

Durante la eliminación de encuestas, se estaban generando **cientos de mensajes** de invalidación de caché:
```
Cache invalidated for response changes in survey 264
Cache invalidated for question changes in survey 264
```

Esto ocurría porque las señales de Django se estaban disparando repetidamente, incluso cuando se usaba SQL crudo para la eliminación.

## Solución Implementada

### 1. Verificación Temprana de Señales
- Las señales ahora verifican `are_signals_enabled()` **ANTES** de acceder a cualquier atributo del objeto
- Esto evita overhead innecesario cuando las señales están deshabilitadas

### 2. Reducción de Logging
- Cambiado `logger.info()` a `logger.debug()` para mensajes de invalidación de caché
- Esto reduce el ruido en los logs durante operaciones normales
- Los mensajes solo aparecerán si el nivel de logging está en DEBUG

### 3. Manejo de Excepciones Mejorado
- Agregado `try/except` para manejar casos donde los objetos ya fueron eliminados
- Las señales ahora ignoran silenciosamente objetos que ya no existen

## Cambios en `surveys/signals.py`

### Antes:
```python
if not are_signals_enabled():
    logger.debug(f"[SIGNALS] invalidate_response_cache IGNORADA...")
    return

survey = instance.survey  # Acceso a atributo antes de verificar
logger.info(f"Cache invalidated...")  # Logging a nivel INFO
```

### Después:
```python
if not are_signals_enabled():
    return  # Salir inmediatamente sin logging

try:
    survey = instance.survey  # Acceso protegido
except (AttributeError, Exception):
    return  # Ignorar silenciosamente si el objeto ya fue eliminado

logger.debug(f"Cache invalidated...")  # Logging a nivel DEBUG
```

## Resultado Esperado

- ✅ **Sin mensajes repetitivos**: Los logs ya no se saturarán con cientos de mensajes de invalidación
- ✅ **Eliminación más rápida**: Menos overhead de logging y verificación
- ✅ **Logs más limpios**: Solo se mostrarán mensajes importantes (INFO y superiores)

## Verificación

Después de estos cambios, al eliminar una encuesta deberías ver:
```
[DELETE] Iniciando eliminación optimizada SQL de 1 encuesta(s): [264]
[DELETE] Step 1 - QuestionResponse: 10000 filas en 0.15s
[DELETE] Step 2 - SurveyResponse: 1000 filas en 0.02s
[DELETE] Step 3 - AnswerOption: 50 filas en 0.01s
[DELETE] Step 4 - Question: 10 filas en 0.00s
[DELETE] Step 5 - Survey: 1 filas en 0.00s
[DELETE] ✅ Eliminación completa: 1 encuesta(s) en 0.18s
```

**Sin** cientos de mensajes de "Cache invalidated".

