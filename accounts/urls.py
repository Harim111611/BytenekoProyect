from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import ByteLoginView

urlpatterns = [
    path('login/',  ByteLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
]
