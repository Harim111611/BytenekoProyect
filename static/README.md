# Static - Archivos Estáticos (CSS, JS, Imágenes)

Este directorio contiene los archivos estáticos de la aplicación.

## Estructura

Los archivos estáticos se organizan por tipo:

- **css/**: Hojas de estilo CSS
- **js/**: Archivos JavaScript
- **images/**: Imágenes PNG, JPG, SVG, etc.
- **fonts/**: Fuentes personalizadas
- **vendor/**: Librerías de terceros (Bootstrap, jQuery, etc.)

## Colecta de Archivos Estáticos

En producción, los archivos estáticos se recopilan con:

```bash
python manage.py collectstatic
```

Esto copia todos los archivos estáticos a un directorio central para servir eficientemente.

## Configuración

En Django settings:
- `STATIC_URL = '/static/'`: URL base para archivos estáticos
- `STATIC_ROOT`: Directorio donde se recopilan para producción
- `STATICFILES_DIRS`: Directorios adicionales de archivos estáticos

## WhiteNoise

Se usa WhiteNoise para servir archivos estáticos de forma eficiente en producción:
- Compresión Gzip y Brotli automática
- Cache headers optimizados
- No requiere servidor web separado

## Optimización

- Usar minificadores para CSS y JavaScript
- Optimizar imágenes
- Usar CDN en producción (CloudFront, Cloudflare, etc.)
