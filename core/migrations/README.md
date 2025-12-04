# Core Migrations - Migraciones de Base de Datos

Este directorio contiene las migraciones de Django que versionan cambios en modelos de core.

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
python manage.py makemigrations core

# Con nombre personalizado
python manage.py makemigrations core --name add_custom_fields
```

## Aplicar Migraciones

```bash
# Aplicar todas las migraciones pendientes
python manage.py migrate

# Aplicar solo migraciones de core
python manage.py migrate core

# Revertir a migración específica
python manage.py migrate core 0003
```

## Ver Estado

```bash
# Ver migraciones aplicadas
python manage.py showmigrations

# Ver migraciones pendientes
python manage.py showmigrations --plan

# Ver migraciones de core
python manage.py showmigrations core
```

## Estructura de Migración

```python
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='custommodel',
            name='new_field',
            field=models.CharField(max_length=100),
        ),
    ]
```

## Mejores Prácticas

1. **Una migración por cambio**
2. **Nombres descriptivos**
3. **No editar migraciones aplicadas**
4. **Probar en desarrollo primero**
5. **Revisar con el equipo**

## Flujo de Trabajo

```bash
# 1. Cambiar model
# 2. Crear migración
python manage.py makemigrations core

# 3. Revisar migración en editor
# 4. Aplicar localmente
python manage.py migrate core

# 5. Testear
pytest

# 6. Commit
git add core/migrations/
git commit -m "migrations: add new fields"

# 7. Empujar
git push
```

## Referencias

- [Django Migrations Documentation](https://docs.djangoproject.com/en/stable/topics/migrations/)
