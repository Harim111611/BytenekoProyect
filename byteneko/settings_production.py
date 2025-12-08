"""
Compat shim for historical references to `byteneko.settings_production`.

Algunos despliegues o scripts antiguos pueden usar el nombre
"byteneko.settings_production" (con guion bajo). Para mantener compatibilidad
creamos este archivo que simplemente importa la configuración nueva.

No añadir lógica sensible aquí; esto solo reexporta las variables del
archivo de configuración moderno `byteneko.settings.production`.
"""
import importlib
import warnings

try:
    # Intentar importar la configuración moderna
    production = importlib.import_module('byteneko.settings.production')
    # Reexportar nombres públicos
    for attr in dir(production):
        if attr.isupper():
            globals()[attr] = getattr(production, attr)
except Exception as exc:
    warnings.warn(
        "No se pudo cargar byteneko.settings.production desde settings_production shim: %s" % exc
    )
    # Fallback: intentar cargar base para evitar fallo completo
    try:
        base = importlib.import_module('byteneko.settings.base')
        for attr in dir(base):
            if attr.isupper():
                globals()[attr] = getattr(base, attr)
    except Exception:
        # Re-raise la excepción original para ayudar al diagnóstico
        raise
