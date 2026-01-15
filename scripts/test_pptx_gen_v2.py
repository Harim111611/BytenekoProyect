
import os
import sys
import django
from datetime import date

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings')
django.setup()

from core.reports.pptx_generator import generate_full_pptx_report

def run_test():
    print("Starting PPTX Generation Test...")
    
    # Mock Data
    survey_mock = {'title': 'Encuesta de Satisfacción 2024 con un título extremadamente largo para probar el ajuste de texto en la portada del reporte'}
    
    analysis_mock = [
        {
            'order': 1,
            'text': '¿Qué tan satisfecho estás con el servicio?',
            'type': 'scale',
            'insight_data': {
                'avg': 8.5,
                'trend_delta': 12.5,
                'narrative': 'La satisfacción ha mejorado considerablemente respecto al Q3.',
                'mood': 'EXCELENTE'
            },
            'chart_labels': ['1', '2', '3', '4', '5'],
            'chart_data': [2, 5, 10, 20, 50]
        },
        {
            'order': 2,
            'text': '¿Qué aspecto valorarías más?',
            'type': 'single',
            'insight_data': {
                'top_option': {'option': 'Rapidez y eficiencia extremas en la entrega', 'count': 45},
                'total': 100,
                'narrative': 'La rapidez es el factor clave para los usuarios.',
                'mood': 'NEUTRO'
            },
            'chart_labels': ['Rapidez', 'Calidad', 'Precio'],
            'chart_data': [45, 30, 25]
        },
        {
            'order': 3,
            'text': 'Comentarios adicionales',
            'type': 'text',
            'insight_data': {
                'narrative': 'Los usuarios piden más integraciones.',
                'mood': 'CRITICO'
            }
        }
    ]
    
    try:
        pdf_buffer = generate_full_pptx_report(
            survey=survey_mock,
            analysis_data=analysis_mock,
            kpi_satisfaction_avg=8.7,
            total_responses=120,
            start_date="2024-01-01",
            end_date="2024-03-30"
        )
        
        size = pdf_buffer.getbuffer().nbytes
        print(f"SUCCESS: PPTX Generated. Size: {size} bytes")
        
        # Save for manual inspection if needed
        output_path = "test_output_v2.pptx"
        with open(output_path, "wb") as f:
            f.write(pdf_buffer.getvalue())
        print(f"Saved to {output_path}")
        
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_test()
