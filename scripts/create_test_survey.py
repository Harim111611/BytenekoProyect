"""
Create test survey with 10 questions for CSV import testing.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings')
django.setup()

from django.contrib.auth import get_user_model
from surveys.models import Survey, Question, AnswerOption

User = get_user_model()

# Get or create test user
user, created = User.objects.get_or_create(
    username='admin',
    defaults={
        'email': 'admin@byteneko.com',
        'is_staff': True,
        'is_superuser': True
    }
)
if created:
    user.set_password('admin')
    user.save()
    print(f'✅ Created user: admin (password: admin)')
else:
    print(f'ℹ️  Using existing user: admin')

# Create survey
survey = Survey.objects.create(
    title='Test Survey - 10k Import',
    description='Survey for testing CSV import with 10,000 responses',
    author=user,
    status='active',
    category='testing'
)
print(f'✅ Created survey ID: {survey.id}')

# Create 10 questions
questions_data = [
    # Multiple choice (1-3)
    {
        'text': '¿Cómo calificarías el servicio?',
        'question_type': 'multiple_choice',
        'order': 1,
        'options': ['Excelente', 'Muy bueno', 'Bueno', 'Regular', 'Malo']
    },
    {
        'text': '¿Recomendarías nuestro producto?',
        'question_type': 'multiple_choice',
        'order': 2,
        'options': ['Excelente', 'Muy bueno', 'Bueno', 'Regular', 'Malo']
    },
    {
        'text': '¿Cómo fue tu experiencia?',
        'question_type': 'multiple_choice',
        'order': 3,
        'options': ['Excelente', 'Muy bueno', 'Bueno', 'Regular', 'Malo']
    },
    
    # Ratings (4-6)
    {
        'text': 'Califica del 1 al 5 la calidad',
        'question_type': 'rating',
        'order': 4,
        'options': []
    },
    {
        'text': 'Califica del 1 al 5 el precio',
        'question_type': 'rating',
        'order': 5,
        'options': []
    },
    {
        'text': 'Califica del 1 al 5 la atención',
        'question_type': 'rating',
        'order': 6,
        'options': []
    },
    
    # Yes/No (7-8)
    {
        'text': '¿Volverías a comprar?',
        'question_type': 'multiple_choice',
        'order': 7,
        'options': ['Sí', 'No']
    },
    {
        'text': '¿Fue fácil el proceso?',
        'question_type': 'multiple_choice',
        'order': 8,
        'options': ['Sí', 'No']
    },
    
    # Text (9-10)
    {
        'text': 'Comentarios adicionales',
        'question_type': 'text',
        'order': 9,
        'options': []
    },
    {
        'text': 'Sugerencias',
        'question_type': 'textarea',
        'order': 10,
        'options': []
    }
]

for q_data in questions_data:
    question = Question.objects.create(
        survey=survey,
        text=q_data['text'],
        question_type=q_data['question_type'],
        order=q_data['order'],
        required=False
    )
    
    # Create answer options
    for option_text in q_data['options']:
        AnswerOption.objects.create(
            question=question,
            text=option_text,
            order=q_data['options'].index(option_text) + 1
        )
    
    print(f'  ✅ Question {q_data["order"]}: {q_data["text"][:50]}... ({q_data["question_type"]})')

print(f'\n✅ Survey created successfully!')
print(f'\nNext steps:')
print(f'1. Generate CSV: python scripts/generate_test_csv.py')
print(f'2. Import CSV: python manage.py import_csv_fast test_10k_responses.csv --survey-id={survey.id}')
print(f'\nTo test deletion:')
print(f'   Delete survey ID {survey.id} from the web interface')
