"""Management command to create a CSV-import friendly test survey."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from surveys.models import AnswerOption, Question, Survey

User = get_user_model()


class Command(BaseCommand):
    help = 'Create a test survey with 10 questions for CSV import testing.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--username',
            default='admin',
            help='Username that will own the survey (default: admin).',
        )
        parser.add_argument(
            '--password',
            default='admin',
            help='Password to set if the user is created (default: admin).',
        )
        parser.add_argument(
            '--email',
            default='admin@byteneko.com',
            help='Email for the created user (default: admin@byteneko.com).',
        )
        parser.add_argument(
            '--title',
            default='Test Survey - 10k Import',
            help='Title for the generated survey.',
        )

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']
        email = options['email']
        title = options['title']

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': email,
                'is_staff': True,
                'is_superuser': True,
            },
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Created user: {username} (password: {password})'))
        else:
            self.stdout.write(self.style.WARNING(f'Using existing user: {username}'))

        survey = Survey.objects.create(
            title=title,
            description='Survey for testing CSV import with 10,000 responses',
            author=user,
            status=Survey.STATUS_ACTIVE,
            category='testing',
        )
        self.stdout.write(self.style.SUCCESS(f'Created survey ID: {survey.id}'))

        questions_data = [
            # Multiple choice (1-3)
            {
                'text': '¿Cómo calificarías el servicio?',
                'type': 'single',
                'order': 1,
                'options': ['Excelente', 'Muy bueno', 'Bueno', 'Regular', 'Malo'],
            },
            {
                'text': '¿Recomendarías nuestro producto?',
                'type': 'single',
                'order': 2,
                'options': ['Excelente', 'Muy bueno', 'Bueno', 'Regular', 'Malo'],
            },
            {
                'text': '¿Cómo fue tu experiencia?',
                'type': 'single',
                'order': 3,
                'options': ['Excelente', 'Muy bueno', 'Bueno', 'Regular', 'Malo'],
            },
            # Ratings (4-6)
            {
                'text': 'Califica del 1 al 5 la calidad',
                'type': 'scale',
                'order': 4,
            },
            {
                'text': 'Califica del 1 al 5 el precio',
                'type': 'scale',
                'order': 5,
            },
            {
                'text': 'Califica del 1 al 5 la atención',
                'type': 'scale',
                'order': 6,
            },
            # Yes/No (7-8)
            {
                'text': '¿Volverías a comprar?',
                'type': 'single',
                'order': 7,
                'options': ['Sí', 'No'],
            },
            {
                'text': '¿Fue fácil el proceso?',
                'type': 'single',
                'order': 8,
                'options': ['Sí', 'No'],
            },
            # Text (9-10)
            {
                'text': 'Comentarios adicionales',
                'type': 'text',
                'order': 9,
            },
            {
                'text': 'Sugerencias',
                'type': 'text',
                'order': 10,
            },
        ]

        for qdata in questions_data:
            question = Question.objects.create(
                survey=survey,
                text=qdata['text'],
                type=qdata['type'],
                order=qdata['order'],
                is_required=False,
            )

            for opt_order, option_text in enumerate(qdata.get('options', []), start=1):
                AnswerOption.objects.create(
                    question=question,
                    text=option_text,
                    order=opt_order,
                )
            self.stdout.write(self.style.SUCCESS(f"  ✓ Question {qdata['order']}: {qdata['text'][:50]}"))

        self.stdout.write(
            self.style.SUCCESS(
                '\nSurvey created successfully!\n'
                f'ID: {survey.id}\n'
                f'Title: {survey.title}\n'
                'Questions: 10\n'
                f'Answer Options: {AnswerOption.objects.filter(question__survey=survey).count()}\n'
            )
        )
        self.stdout.write(
            'Next steps:\n'
            ' 1. Generate CSV: python scripts/generate_test_csv.py\n'
            f' 2. Import CSV: python manage.py import_csv_fast test_10k_responses.csv --survey-id={survey.id}\n'
        )
