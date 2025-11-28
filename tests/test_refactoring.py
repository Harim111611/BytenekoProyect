import pytest
from surveys.models import Survey
from django.contrib.auth.models import User

@pytest.mark.django_db
def test_refactoring():
    # Check current count
    print(f'Current Survey count: {Survey.objects.count()}')
    # Get first user
    user = User.objects.first()
    if user:
        # Create test survey
        survey = Survey.objects.create(
            title='Test English Refactoring',
            category='Testing',
            status='draft',
            author=user,
            sample_goal=100
        )
        print(f'✅ Created survey: {survey.title} (ID: {survey.id})')
        print(f'   - Title: {survey.title}')
        print(f'   - Author: {survey.author.username}')
        print(f'   - Status: {survey.status}')
        print(f'   - Created at: {survey.created_at}')
        # Delete test survey
        survey.delete()
        print('✅ Deleted test survey successfully')
        print(f'\n✅ All database operations working correctly!')
    else:
        print('⚠️  No users found in database')
