"""
Script para probar la velocidad de eliminación optimizada.
Compara Django ORM .delete() vs fast_delete_surveys().

Uso:
    docker exec byteneko_app python scripts/test_delete_speed.py
"""
import os
import sys
import django
import time
from pathlib import Path

# Setup Django
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings.local')
django.setup()

from django.contrib.auth import get_user_model
from django.db import transaction
from surveys.models import Survey, Question, AnswerOption, SurveyResponse, QuestionResponse
from surveys.utils.delete_optimizer import fast_delete_surveys

User = get_user_model()


def create_test_survey(user, response_count=100):
    """Crear encuesta de prueba con respuestas."""
    with transaction.atomic():
        survey = Survey.objects.create(
            title=f"Test Survey - {response_count} responses - {int(time.time())}",
            description="Performance test survey",
            author=user,
            status='draft'
        )
        
        # Crear 5 preguntas con opciones
        questions = []
        for i in range(5):
            q = Question.objects.create(
                survey=survey,
                text=f"Question {i+1}",
                type='single',
                order=i
            )
            questions.append(q)
            
            # 3 opciones por pregunta
            for j in range(3):
                AnswerOption.objects.create(
                    question=q,
                    text=f"Option {j+1}",
                    order=j
                )
        
        # Crear respuestas
        for i in range(response_count):
            sr = SurveyResponse.objects.create(survey=survey)
            for q in questions:
                # Seleccionar primera opción
                option = q.options.first()
                QuestionResponse.objects.create(
                    survey_response=sr,
                    question=q,
                    selected_option=option
                )
        
        print(f"✅ Encuesta creada: {survey.id} con {response_count} respuestas")
        return survey


def test_django_orm_delete(user, response_count):
    """Probar .delete() de Django ORM (LENTO)."""
    print(f"\n🐌 Test 1: Django ORM .delete() - {response_count} respuestas")
    survey = create_test_survey(user, response_count)
    survey_id = survey.id
    
    start = time.time()
    survey.delete()  # Usa CASCADE, activa señales
    elapsed = time.time() - start
    
    print(f"⏱️  Tiempo: {elapsed:.3f}s")
    return elapsed


def test_fast_delete(user, response_count):
    """Probar fast_delete_surveys() optimizado (RÁPIDO)."""
    print(f"\n🚀 Test 2: fast_delete_surveys() - {response_count} respuestas")
    survey = create_test_survey(user, response_count)
    survey_id = survey.id
    
    start = time.time()
    result = fast_delete_surveys([survey_id])
    elapsed = time.time() - start
    
    if result['status'] == 'SUCCESS':
        print(f"✅ Eliminadas: {result['deleted']} encuestas")
        if 'details' in result:
            details = result['details']
            print(f"   - {details['question_responses']} respuestas individuales")
            print(f"   - {details['responses']} respuestas de encuesta")
            print(f"   - {details['options']} opciones")
            print(f"   - {details['questions']} preguntas")
    
    print(f"⏱️  Tiempo: {elapsed:.3f}s")
    return elapsed


def main():
    print("=" * 60)
    print("🧪 TEST DE VELOCIDAD DE ELIMINACIÓN")
    print("=" * 60)
    
    # Obtener o crear usuario de prueba
    user, _ = User.objects.get_or_create(
        username='test_delete_user',
        defaults={'email': 'test@delete.com'}
    )
    
    # Pruebas con diferentes tamaños
    test_sizes = [10, 50, 100]
    
    results = []
    for size in test_sizes:
        print(f"\n{'=' * 60}")
        print(f"📊 Pruebas con {size} respuestas")
        print(f"{'=' * 60}")
        
        # Test ORM
        orm_time = test_django_orm_delete(user, size)
        
        # Test optimizado
        fast_time = test_fast_delete(user, size)
        
        # Calcular mejora
        speedup = orm_time / fast_time if fast_time > 0 else 0
        results.append({
            'size': size,
            'orm': orm_time,
            'fast': fast_time,
            'speedup': speedup
        })
        
        print(f"\n📈 Mejora: {speedup:.1f}x más rápido")
    
    # Resumen final
    print(f"\n{'=' * 60}")
    print("📊 RESUMEN DE RESULTADOS")
    print(f"{'=' * 60}")
    print(f"{'Respuestas':<15} {'ORM (s)':<15} {'Optimizado (s)':<15} {'Mejora':<10}")
    print("-" * 60)
    for r in results:
        print(f"{r['size']:<15} {r['orm']:<15.3f} {r['fast']:<15.3f} {r['speedup']:.1f}x")
    
    avg_speedup = sum(r['speedup'] for r in results) / len(results)
    print(f"\n⚡ Promedio de mejora: {avg_speedup:.1f}x más rápido")
    
    print("\n✅ Tests completados!")


if __name__ == '__main__':
    main()
