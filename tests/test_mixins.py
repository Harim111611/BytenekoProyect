import pytest
from django.contrib.auth.models import User, AnonymousUser
from django.test import RequestFactory
from django.core.exceptions import PermissionDenied
from core.mixins import OwnerRequiredMixin, EncuestaQuerysetMixin, CacheMixin
from surveys.models import Survey

@pytest.mark.django_db
def test_owner_required_mixin_allows_owner():
    user = User.objects.create_user(username='owner', password='123')
    survey = Survey.objects.create(title='Test', author=user)
    factory = RequestFactory()
    request = factory.get('/')
    request.user = user
    class DummyView(OwnerRequiredMixin):
        def __init__(self, request, pk):
            self.request = request
            self.kwargs = {'pk': pk}
    view = DummyView(request, survey.pk)
    assert view.test_func() is True

@pytest.mark.django_db
def test_owner_required_mixin_denies_non_owner():
    owner = User.objects.create_user(username='owner', password='123')
    other = User.objects.create_user(username='other', password='123')
    survey = Survey.objects.create(title='Test', author=owner)
    factory = RequestFactory()
    request = factory.get('/')
    request.user = other
    class DummyView(OwnerRequiredMixin):
        def __init__(self, request, pk):
            self.request = request
            self.kwargs = {'pk': pk}
    view = DummyView(request, survey.pk)
    assert view.test_func() is False
    with pytest.raises(PermissionDenied):
        view.handle_no_permission()

@pytest.mark.django_db
def test_encuesta_queryset_mixin_returns_user_surveys():
    user = User.objects.create_user(username='user', password='123')
    Survey.objects.create(title='A', author=user)
    Survey.objects.create(title='B', author=user)
    factory = RequestFactory()
    request = factory.get('/')
    request.user = user
    class DummyView(EncuestaQuerysetMixin):
        def __init__(self, request):
            self.request = request
    view = DummyView(request)
    qs = view.get_queryset()
    assert qs.count() == 2
    assert all(s.author == user for s in qs)

class DummyCacheView(CacheMixin):
    def __init__(self, user_id):
        class DummyRequest:
            def __init__(self, user_id):
                class DummyUser:
                    id = user_id
                self.user = DummyUser()
        self.request = DummyRequest(user_id)


def test_cache_mixin_generates_key():
    view = DummyCacheView(user_id=42)
    key = view.get_cache_key('dashboard', foo='bar', x=1)
    assert key.startswith('dashboard_user_42')
    assert 'foo_bar' in key and 'x_1' in key

def test_cache_mixin_timeout_default():
    view = DummyCacheView(user_id=1)
    assert view.get_cache_timeout() == 300
