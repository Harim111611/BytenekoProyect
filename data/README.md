# Data - Datos de Prueba y Backups

Este directorio contiene datos para desarrollo, testing y backups.

## Contenido

- **backup_clean.json**: Backup limpio de datos de la base de datos
- **backup_sqlite.json**: Backup de la base de datos SQLite local
- **samples/**: Datos de muestra para testing

## Backups

### Crear backup
```bash
python manage.py dumpdata > data/backup_$(date +%Y%m%d_%H%M%S).json
```

### Restaurar backup
```bash
python manage.py loaddata data/backup_clean.json
```

## Datos de Muestra

La carpeta `samples/` contiene:
- Archivos CSV de ejemplo
- Archivos JSON de ejemplo
- Otros datos para testing

## Consideraciones de Seguridad

⚠️ **IMPORTANTE**: 
- No incluir datos sensibles en esta carpeta
- No hacer commit de backups con información personal
- Usar `.gitignore` para datos confidenciales

## Uso en Testing

Para usar datos de muestra en tests:

```python
from django.core.management import call_command

def setup_test_data():
    call_command('loaddata', 'data/samples/test_data.json')
```

## Migraciones

Los cambios de estructura de base de datos se manejan con migraciones:

```bash
# Crear migración
python manage.py makemigrations

# Aplicar migraciones
python manage.py migrate
```

Los archivos de migración están en:
- `core/migrations/`
- `surveys/migrations/`
