# Surveys Migrations - Migraciones de Base de Datos

Este directorio contiene las migraciones de Django que versionan cambios en modelos de encuestas.

## ¿Qué es una Migración?

Una migración es un archivo Python que describe cambios en la estructura de base de datos.

## Archivos

- **0001_initial.py**: Migración inicial
- **0002_*.py**: Cambios posteriores
- **__init__.py**: Inicializador

## Crear Migración

```bash
# Detectar cambios en models.py
python manage.py makemigrations

# Crear migración específica
python manage.py makemigrations surveys

# Con nombre personalizado
python manage.py makemigrations surveys --name add_field_description
```

## Aplicar Migraciones

```bash
# Aplicar todas las migraciones pendientes
python manage.py migrate

# Aplicar solo migraciones de surveys
python manage.py migrate surveys

# Revertir a migración específica
python manage.py migrate surveys 0005
```

## Ver Estado

```bash
# Ver migraciones aplicadas
python manage.py showmigrations

# Ver migraciones pendientes
python manage.py showmigrations --plan
```

## Estructura de Migración

```python
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='survey',
            name='description',
            field=models.TextField(blank=True, null=True),
        ),
    ]
```

## Mejores Prácticas

1. **Una migración por cambio**: Facilita revertir
2. **Nombres descriptivos**: Indicar qué cambió
3. **No editar migraciones aplicadas**: Crear nuevas
4. **Probar migraciones**: En desarrollo y staging
5. **Documentar cambios complejos**: Agregar comentarios

## Problemas Comunes

### Conflictos de migraciones
```bash
# Si hay múltiples migraciones de diferentes ramas
python manage.py makemigrations --merge
```

### Revertir cambios
```bash
# Revertir a versión anterior
python manage.py migrate surveys 0004
```

### Base de datos vacía
```bash
# Aplicar todas las migraciones
python manage.py migrate
```

## Testing

```python
from django.test import TestCase
from django.db import connection

class MigrationTest(TestCase):
    def test_migration(self):
        # Verificar que la migración se aplicó
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM surveys_survey LIMIT 1")
```

## Documentación

- [Django Migrations](https://docs.djangoproject.com/en/stable/topics/migrations/)
- [Migration Operations](https://docs.djangoproject.com/en/stable/ref/migration-operations/)
