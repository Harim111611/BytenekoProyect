import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings')
django.setup()

from surveys.models import Survey
from django.contrib.auth.models import User

u = User.objects.first()
encuestas = Survey.objects.filter(author=u).order_by('-created_at')

print(f"\nTotal de encuestas: {encuestas.count()}\n")
print("="*80)

for e in encuestas:
    print(f"\nTítulo: {e.title}")
    print(f"  - Fecha: {e.created_at}")
    print(f"  - Preguntas: {e.questions.count()}")
    print(f"  - Respuestas: {e.responses.count()}")
    print(f"  - Estado: {e.status}")

print("\n" + "="*80)
