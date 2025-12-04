# Surveys Management Commands - Comandos Personalizados

Este directorio contiene los comandos personalizados de Django para el módulo surveys.

## Estructura

```
commands/
├── __init__.py
├── comando1.py
├── comando2.py
└── ...
```

## Ejecución

```bash
python manage.py nombre_comando [opciones]
```

## Plantilla de Comando

```python
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Descripción breve del comando'
    
    def add_arguments(self, parser):
        parser.add_argument('--flag', action='store_true', help='Descripción')
    
    def handle(self, *args, **options):
        # Lógica del comando
        self.stdout.write(self.style.SUCCESS('¡Hecho!'))
```

## Mejores Prácticas

1. **Nombres descriptivos**: usar guiones bajos
2. **Ayuda clara**: documentar opciones
3. **Validación**: verificar entrada
4. **Manejo de errores**: try/except
5. **Feedback**: informar progreso

## Referencias

- [Django Management Commands](https://docs.djangoproject.com/en/stable/howto/custom-management-commands/)
