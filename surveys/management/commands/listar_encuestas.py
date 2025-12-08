"""Lista encuestas con detalles básicos para un usuario."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from surveys.models import Survey

User = get_user_model()


class Command(BaseCommand):
    help = 'Lista encuestas detalladas para un usuario (por defecto, el primero).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            help='Usuario para filtrar encuestas (default: primer usuario).',
        )

    def handle(self, *args, **options):
        username = options.get('username')
        if username:
            user = User.objects.filter(username=username).first()
            if not user:
                raise CommandError(f'Usuario {username} no existe')
        else:
            user = User.objects.order_by('id').first()
            if not user:
                raise CommandError('No hay usuarios en la base de datos')

        encuestas = (
            Survey.objects.filter(author=user)
            .annotate(question_count=Count('questions'), response_count=Count('responses'))
            .order_by('-created_at')
        )

        self.stdout.write(f"\nTotal de encuestas: {encuestas.count()}\n")
        self.stdout.write('=' * 80)

        for encuesta in encuestas:
            self.stdout.write(
                f"\nTítulo: {encuesta.title}\n"
                f"  - Fecha: {encuesta.created_at}\n"
                f"  - Preguntas: {encuesta.question_count}\n"
                f"  - Respuestas: {encuesta.response_count}\n"
                f"  - Estado: {encuesta.status}\n"
            )

        self.stdout.write('\n' + '=' * 80)
