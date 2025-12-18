import json

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse

from surveys.models import Survey


@pytest.mark.django_db
def test_validate_status_transition_blocks_active_to_draft():
    user = User.objects.create_user(username='u1', password='pw')
    survey = Survey.objects.create(title='S', author=user, status=Survey.STATUS_ACTIVE)

    with pytest.raises(ValidationError, match='Transici'):
        survey.validate_status_transition(Survey.STATUS_DRAFT)


@pytest.mark.django_db
def test_validate_status_transition_blocks_closed_to_active():
    user = User.objects.create_user(username='u2', password='pw')
    survey = Survey.objects.create(title='S', author=user, status=Survey.STATUS_CLOSED)

    with pytest.raises(ValidationError, match='Transici'):
        survey.validate_status_transition(Survey.STATUS_ACTIVE)


@pytest.mark.django_db
def test_change_status_endpoint_rejects_invalid_transition(client):
    user = User.objects.create_user(username='u3', password='pw')
    client.force_login(user)

    survey = Survey.objects.create(title='S', author=user, status=Survey.STATUS_ACTIVE)
    url = reverse('surveys:change_status', kwargs={'public_id': survey.public_id})

    resp = client.post(
        url,
        data=json.dumps({'status': Survey.STATUS_DRAFT}),
        content_type='application/json',
    )

    assert resp.status_code == 400
    survey.refresh_from_db()
    assert survey.status == Survey.STATUS_ACTIVE


@pytest.mark.django_db
def test_change_status_endpoint_allows_paused_to_active(client):
    user = User.objects.create_user(username='u4', password='pw')
    client.force_login(user)

    survey = Survey.objects.create(title='S', author=user, status=Survey.STATUS_PAUSED)
    url = reverse('surveys:change_status', kwargs={'public_id': survey.public_id})

    resp = client.post(
        url,
        data=json.dumps({'status': Survey.STATUS_ACTIVE}),
        content_type='application/json',
    )

    assert resp.status_code == 200
    survey.refresh_from_db()
    assert survey.status == Survey.STATUS_ACTIVE
