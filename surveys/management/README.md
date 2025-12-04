# Surveys Management - Comandos Personalizados de Django

Este subdirectorio contiene comandos personalizados que se ejecutan con `manage.py`.

## Comandos Disponibles

Los comandos están organizados en la carpeta `commands/`:

```bash
# Ejecutar comando
python manage.py nombre_comando
```

## Estructura

```
management/
├── __init__.py
└── commands/
    ├── __init__.py
    ├── comando1.py
    ├── comando2.py
    └── ...
```

## Creando un Comando

```python
# management/commands/mi_comando.py
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Descripción de lo que hace el comando'
    
    def add_arguments(self, parser):
        parser.add_argument('--opcion', type=str, help='Descripción')
    
    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Comando ejecutado exitosamente')
        )
```

## Ejecución

```bash
# Sin argumentos
python manage.py mi_comando

# Con argumentos
python manage.py mi_comando --opcion valor

# Mostrar ayuda
python manage.py mi_comando --help
```

## Casos de Uso

- Importación de datos
- Limpieza de base de datos
- Migraciones personalizadas
- Reportes programados
- Mantenimiento del sistema

## Comandos Comunes en Django

```bash
# Migraciones
python manage.py migrate

# Crear superusuario
python manage.py createsuperuser

# Cargar datos
python manage.py loaddata datos.json

# Volcar datos
python manage.py dumpdata > datos.json

# Limpiar caché
python manage.py clear_cache
```

## Testing de Comandos

```python
from django.core.management import call_command
from io import StringIO

def test_comando():
    out = StringIO()
    call_command('mi_comando', stdout=out)
    assert 'éxito' in out.getvalue()
```

## Mejores Prácticas

- Usar `add_arguments()` para opciones
- Mantener comandos simples
- Usar `self.stdout.write()` para output
- Manejar excepciones apropiadamente
- Documentar el comando
