from django.contrib.auth.views import LoginView
from .forms import ByteAuthForm

class ByteLoginView(LoginView):
    template_name = 'accounts/login.html'
    authentication_form = ByteAuthForm
    redirect_authenticated_user = True
