from surveys.models import Survey
from django.contrib.auth.models import User

u = User.objects.first()
print(f'Total encuestas: {Survey.objects.filter(author=u).count()}')
print('\nEncuestas importadas:')
for e in Survey.objects.filter(author=u).order_by('-created_at'):
    print(f'- {e.title} ({e.questions.count()} preguntas, {e.responses.count()} respuestas)')
