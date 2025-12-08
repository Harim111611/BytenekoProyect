"""Summarize surveys for a given user."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from surveys.models import Survey

User = get_user_model()


class Command(BaseCommand):
    help = 'Print total surveys and counts for a given user (default: first user).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            help='Username to inspect. Defaults to the first user.',
        )

    def handle(self, *args, **options):
        username = options.get('username')

        if username:
            user = User.objects.filter(username=username).first()
            if not user:
                raise CommandError(f'User {username} not found')
        else:
            user = User.objects.order_by('id').first()
            if not user:
                raise CommandError('No users found in the database')

        surveys = (
            Survey.objects.filter(author=user)
            .annotate(question_count=Count('questions'), response_count=Count('responses'))
            .order_by('-created_at')
        )

        self.stdout.write(f'Total encuestas para {user.username}: {surveys.count()}')
        self.stdout.write('\nEncuestas:')
        for survey in surveys:
            self.stdout.write(
                f'- {survey.title} '
                f'({survey.question_count} preguntas, {survey.response_count} respuestas)'
            )
