
import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from django.test import Client


@pytest.mark.django_db
def test_dashboard_view_authenticated():
    user = User.objects.create_user(username='testuser', password='testpass')
    client = Client()
    client.login(username='testuser', password='testpass')
    response = client.get(reverse('dashboard'))
    assert response.status_code == 200
    assert 'dashboard' in response.context['page_name']
    assert 'kpis' in response.context


@pytest.mark.django_db
def test_dashboard_results_view_authenticated():
    user = User.objects.create_user(username='testuser', password='testpass')
    client = Client()
    client.login(username='testuser', password='testpass')
    response = client.get(reverse('dashboard_results'))
    assert response.status_code == 200
    assert 'total_responses' in response.context
    assert 'global_satisfaction' in response.context
