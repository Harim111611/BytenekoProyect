import pytest
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from asgiref.sync import async_to_sync
from core.utils.helpers import DateFilterHelper, ResponseDataBuilder, PermissionHelper
from surveys.models import Survey
from datetime import timedelta

@pytest.mark.django_db
def test_date_filter_helper_apply_filters_start_end():
    user = User.objects.create_user(username='user', password='123')
    survey = Survey.objects.create(title='Test', author=user)
    now = timezone.now()
    qs = Survey.objects.all()
    start = (now - timedelta(days=5)).strftime('%Y-%m-%d')
    end = now.strftime('%Y-%m-%d')
    filtered, processed_start = DateFilterHelper.apply_filters(qs, start=start, end=end)
    assert processed_start == start
    assert isinstance(filtered, type(qs))

@pytest.mark.django_db
def test_date_filter_helper_apply_filters_window():
    user = User.objects.create_user(username='user', password='123')
    Survey.objects.create(title='Test', author=user)
    qs = Survey.objects.all()
    filtered, processed_start = DateFilterHelper.apply_filters(qs, window='3')
    assert isinstance(filtered, type(qs))
    assert processed_start is not None

def test_date_filter_helper_build_date_range_label():
    label = DateFilterHelper.build_date_range_label(start='2025-11-01', end='2025-11-10')
    assert 'Desde' in label and 'hasta' in label
    label2 = DateFilterHelper.build_date_range_label(window=7)
    assert 'Últimos' in label2 or 'ultimos' in label2.lower()

@pytest.mark.django_db
def test_permission_helper_verify_survey_access():
    user = User.objects.create_user(username='user', password='123')
    survey = Survey.objects.create(title='Test', author=user)
    # Should not raise
    async_to_sync(PermissionHelper.verify_survey_access)(survey, user)
    other = User.objects.create_user(username='other', password='123')
    with pytest.raises(PermissionDenied):
        async_to_sync(PermissionHelper.verify_survey_access)(survey, other)

@pytest.mark.django_db
def test_permission_helper_verify_survey_is_active():
    user = User.objects.create_user(username='user', password='123')
    survey = Survey.objects.create(title='Test', author=user, status='active')
    assert PermissionHelper.verify_survey_is_active(survey) is True
    survey.status = 'closed'
    assert PermissionHelper.verify_survey_is_active(survey) is False
