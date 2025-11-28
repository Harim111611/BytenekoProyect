import pytest
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings')
django.setup()
from surveys.models import Survey, SurveyResponse
from django.contrib.auth.models import User
from django.core.cache import cache

@pytest.mark.django_db
def test_cache_invalidation():
    print("\n=== Testing Intelligent Cache Invalidation ===\n")
    
    # Get a test user and survey
    user = User.objects.first()
    if not user:
        print("❌ No users found. Create a user first.")
        return
    
    survey = Survey.objects.filter(author=user).first()
    if not survey:
        print("❌ No surveys found. Create a survey first.")
        return
    
    print(f"✓ Using survey: {survey.id} - {survey.title}")
    print(f"✓ Owner: {user.username}\n")
    
    # Test 1: Survey modification invalidates cache
    print("Test 1: Survey modification")
    cache_key = f"survey_analysis_{survey.id}_all_all_all"
    cache.set(cache_key, "test_data", 300)
    print(f"  - Set cache: {cache_key}")
    print(f"  - Cache value: {cache.get(cache_key)}")
    
    survey.save()
    print(f"  - Survey saved")
    
    cached_value = cache.get(cache_key)
    if cached_value is None:
        print(f"  ✅ Cache invalidated correctly!")
    else:
        print(f"  ❌ Cache still exists: {cached_value}")
    
    # Test 2: Dashboard cache invalidation
    print("\nTest 2: Dashboard cache")
    dashboard_key = f"dashboard_data_user_{user.id}"
    cache.set(dashboard_key, {"test": "data"}, 300)
    print(f"  - Set cache: {dashboard_key}")
    
    survey.save()
    print(f"  - Survey saved")
    
    if cache.get(dashboard_key) is None:
        print(f"  ✅ Dashboard cache invalidated!")
    else:
        print(f"  ❌ Dashboard cache still exists")
    
    # Test 3: Response cache invalidation
    print("\nTest 3: Response modification")
    stats_key = f"survey_stats_{survey.id}"
    cache.set(stats_key, {"total": 100}, 300)
    print(f"  - Set stats cache: {stats_key}")
    
    # Check if survey has responses
    response = SurveyResponse.objects.filter(survey=survey).first()
    if response:
        response.save()
        print(f"  - Response saved")
        
        if cache.get(stats_key) is None:
            print(f"  ✅ Stats cache invalidated!")
        else:
            print(f"  ❌ Stats cache still exists")
    else:
        print(f"  ⚠️  No responses found, skipping test")
    
    print("\n=== Test Complete ===\n")

if __name__ == '__main__':
    test_cache_invalidation()
