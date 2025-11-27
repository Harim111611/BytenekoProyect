"""
Script to test survey deletion performance with and without signal optimization.
This demonstrates the impact of the DisableSignals context manager.
"""
import os
import sys
import django
import time
from pathlib import Path

# Setup Django environment
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings')
django.setup()

from django.contrib.auth import get_user_model
from surveys.models import Survey, Question, AnswerOption, SurveyResponse, QuestionResponse
from surveys.signals import DisableSignals
from django.core.cache import cache

User = get_user_model()


def create_test_survey(user, response_count=100):
    """Create a test survey with specified number of responses."""
    survey = Survey.objects.create(
        title=f"Test Survey - {response_count} responses",
        description="Performance test survey",
        author=user,
        status='published'
    )
    
    # Create 5 questions
    questions = []
    for i in range(5):
        q = Question.objects.create(
            survey=survey,
            text=f"Question {i+1}",
            type='text',
            order=i
        )
        questions.append(q)
    
    # Create responses
    for i in range(response_count):
        sr = SurveyResponse.objects.create(survey=survey)
        for q in questions:
            QuestionResponse.objects.create(
                survey_response=sr,
                question=q,
                text_response=f"Response {i+1}"
            )
    
    return survey


def test_delete_without_optimization(user, response_count):
    """Test deletion speed WITHOUT signal optimization."""
    print(f"\n{'='*60}")
    print(f"Testing deletion of survey with {response_count} responses")
    print(f"Method: Standard (signals enabled)")
    print(f"{'='*60}")
    
    survey = create_test_survey(user, response_count)
    print(f"Created survey {survey.id} with {response_count} responses")
    
    # Measure deletion time
    start = time.time()
    survey.delete()
    elapsed = time.time() - start
    
    print(f"✓ Deletion completed in {elapsed:.2f} seconds")
    print(f"  Estimated cache operations: {response_count * 6} (6 per response)")
    return elapsed


def test_delete_with_optimization(user, response_count):
    """Test deletion speed WITH signal optimization."""
    print(f"\n{'='*60}")
    print(f"Testing deletion of survey with {response_count} responses")
    print(f"Method: Optimized (signals disabled)")
    print(f"{'='*60}")
    
    survey = create_test_survey(user, response_count)
    print(f"Created survey {survey.id} with {response_count} responses")
    
    # Measure deletion time with optimization
    start = time.time()
    with DisableSignals():
        survey.delete()
    # Manual cache invalidation (just once)
    cache.delete(f"dashboard_data_user_{user.id}")
    elapsed = time.time() - start
    
    print(f"✓ Deletion completed in {elapsed:.2f} seconds")
    print(f"  Cache operations: 1 (single invalidation)")
    return elapsed


def main():
    """Run performance comparison tests."""
    print("\n" + "="*60)
    print("SURVEY DELETION PERFORMANCE TEST")
    print("="*60)
    
    # Get or create test user
    user, _ = User.objects.get_or_create(
        username='performance_test_user',
        defaults={'email': 'test@example.com'}
    )
    
    # Test with small dataset (100 responses)
    print("\n\n🔬 TEST 1: Small Survey (100 responses)")
    time_normal_100 = test_delete_without_optimization(user, 100)
    time_optimized_100 = test_delete_with_optimization(user, 100)
    speedup_100 = time_normal_100 / time_optimized_100 if time_optimized_100 > 0 else 0
    
    print(f"\n📊 Results for 100 responses:")
    print(f"   Normal:    {time_normal_100:.2f}s")
    print(f"   Optimized: {time_optimized_100:.2f}s")
    print(f"   Speedup:   {speedup_100:.1f}x faster")
    
    # Test with medium dataset (1000 responses)
    print("\n\n🔬 TEST 2: Medium Survey (1000 responses)")
    time_normal_1k = test_delete_without_optimization(user, 1000)
    time_optimized_1k = test_delete_with_optimization(user, 1000)
    speedup_1k = time_normal_1k / time_optimized_1k if time_optimized_1k > 0 else 0
    
    print(f"\n📊 Results for 1000 responses:")
    print(f"   Normal:    {time_normal_1k:.2f}s")
    print(f"   Optimized: {time_optimized_1k:.2f}s")
    print(f"   Speedup:   {speedup_1k:.1f}x faster")
    
    # Summary
    print("\n\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Small (100):   {speedup_100:.1f}x speedup")
    print(f"Medium (1000): {speedup_1k:.1f}x speedup")
    print("\n💡 Optimization Impact:")
    print(f"   - Reduces cache operations from N×6 to 1")
    print(f"   - For 10k responses: 60,000 → 1 cache ops (60,000x reduction)")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()
