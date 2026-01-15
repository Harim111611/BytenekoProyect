
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings')
django.setup()

from core.reports.pptx_generator import generate_full_pptx_report

def run_test():
    print("Testing PPTX bounds with extensive data...")
    
    # Mock Data with MANY items to stress-test pagination
    survey_mock = {'title': 'Encuesta de Satisfacción Q1 2024'}
    
    analysis_mock = []
    
    # Create 20 questions to test table pagination
    for i in range(1, 21):
        analysis_mock.append({
            'order': i,
            'text': f'Pregunta {i}: ¿Qué opinas sobre el aspecto #{i} del servicio prestado?',
            'type': 'scale' if i % 3 == 0 else 'single',
            'insight_data': {
                'avg': 7.5 + (i % 3),
                'trend_delta': 5.0 if i % 2 == 0 else -3.0,
                'narrative': f'Esta es una narrativa muy larga para la pregunta {i} que debe ajustarse correctamente dentro de la caja de narrativa sin desbordar los márgenes de la diapositiva. Incluye análisis detallado de tendencias y recomendaciones específicas para mejorar la experiencia del usuario.',
                'mood': 'EXCELENTE' if i % 4 == 0 else 'NEUTRO',
                'top_option': {'option': f'Opción favorita {i}', 'count': 45 + i},
                'total': 100
            },
            'chart_labels': ['Opt A', 'Opt B', 'Opt C', 'Opt D'],
            'chart_data': [20 + i, 30, 25, 25 - i]
        })
    
    try:
        pptx_buffer = generate_full_pptx_report(
            survey=survey_mock,
            analysis_data=analysis_mock,
            kpi_satisfaction_avg=8.2,
            total_responses=250,
            user_name="María González",
            start_date="2024-01-01",
            end_date="2024-03-31",
            include_kpis=True,
            include_table=True,
            include_charts=True
        )
        
        output_path = "test_bounds.pptx"
        with open(output_path, "wb") as f:
            f.write(pptx_buffer.getvalue())
        
        size = pptx_buffer.getbuffer().nbytes
        print(f"✓ PPTX Generated: {size} bytes")
        print(f"✓ Saved to {output_path}")
        print(f"✓ Created {len(analysis_mock)} detail slides + cover + summary slides")
        
    except Exception as e:
        print(f"✗ FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_test()
