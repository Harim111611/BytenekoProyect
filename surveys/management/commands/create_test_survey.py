"""
Management command to create a test survey with 10 questions.
Matches the structure expected by generate_test_csv.py
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from surveys.models import Survey, Question, AnswerOption

User = get_user_model()


class Command(BaseCommand):
    help = 'Create a test survey with 10 questions for CSV import testing'

    def handle(self, *args, **options):
        # Create or get admin user
        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@example.com',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            admin.set_password('admin')
            admin.save()
            self.stdout.write(self.style.SUCCESS(f'Created admin user'))
        
        # Create test survey
        survey = Survey.objects.create(
            title='Test Survey 10k',
            description='Survey for testing CSV import with 10,000 responses',
            author=admin,
            status='active'
        )
        
        # Question 1: Single choice (Favorite Color)
        q1 = Question.objects.create(
            survey=survey,
            text='What is your favorite color?',
            type='single',
            order=1
        )
        for color in ['Red', 'Blue', 'Green', 'Yellow', 'Purple']:
            AnswerOption.objects.create(question=q1, text=color)
        
        # Question 2: Scale (Product Satisfaction)
        q2 = Question.objects.create(
            survey=survey,
            text='Rate your satisfaction with our product',
            type='scale',
            order=2
        )
        
        # Question 3: Single choice (Would Recommend)
        q3 = Question.objects.create(
            survey=survey,
            text='Would you recommend us to a friend?',
            type='single',
            order=3
        )
        for opt in ['Yes', 'No']:
            AnswerOption.objects.create(question=q3, text=opt)
        
        # Question 4: Single choice (Browser)
        q4 = Question.objects.create(
            survey=survey,
            text='Which browser do you use?',
            type='single',
            order=4
        )
        for browser in ['Chrome', 'Firefox', 'Safari', 'Edge']:
            AnswerOption.objects.create(question=q4, text=browser)
        
        # Question 5: Scale (Support Quality)
        q5 = Question.objects.create(
            survey=survey,
            text='How would you rate our support team?',
            type='scale',
            order=5
        )
        
        # Question 6: Single choice (Used Before)
        q6 = Question.objects.create(
            survey=survey,
            text='Have you used our service before?',
            type='single',
            order=6
        )
        for opt in ['Yes', 'No']:
            AnswerOption.objects.create(question=q6, text=opt)
        
        # Question 7: Single choice (Age Group)
        q7 = Question.objects.create(
            survey=survey,
            text='What is your age group?',
            type='single',
            order=7
        )
        for age_group in ['18-25', '26-35', '36-45', '46-55', '56+']:
            AnswerOption.objects.create(question=q7, text=age_group)
        
        # Question 8: Scale (Website Design)
        q8 = Question.objects.create(
            survey=survey,
            text='Rate our website design',
            type='scale',
            order=8
        )
        
        # Question 9: Text (Suggestions)
        q9 = Question.objects.create(
            survey=survey,
            text='Any suggestions for improvement?',
            type='text',
            order=9
        )
        
        # Question 10: Text (Comments)
        q10 = Question.objects.create(
            survey=survey,
            text='Additional comments',
            type='text',
            order=10
        )
        
        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Survey created successfully!'
            f'\n  ID: {survey.id}'
            f'\n  Title: {survey.title}'
            f'\n  Questions: 10'
            f'\n  Answer Options: {AnswerOption.objects.filter(question__survey=survey).count()}'
            f'\n\nNext steps:'
            f'\n  1. python scripts/generate_test_csv.py'
            f'\n  2. python manage.py import_csv_fast test_10k_responses.csv --survey-id={survey.id}'
        ))
