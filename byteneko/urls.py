from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('', include('accounts.urls_home')),              # dashboard
    path('surveys/', include('surveys.urls')),            # <-- nuevo
]
