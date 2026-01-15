
import os
import sys
import django

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings')
django.setup()

from core.reports.pptx_generator import generate_full_pptx_report

def run_test():
    print("Testing Autosize bounds...")
    
    # Text that is EXTREMELY long for a metric
    long_metric_text = "Opción Extremadamente Larga Que Normalmente Rompería El Layout"
    
    # Narrative that is TOO long for the box
    long_narrative = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 20
    
    analysis_mock = [
        {
            'order': 1,
            'text': 'Pregunta de Prueba',
            'type': 'single',
            'insight_data': {
                'top_option': {'option': long_metric_text, 'count': 45},
                'total': 100,
                'narrative': long_narrative,
                'mood': 'NEUTRO'
            },
            'chart_labels': ['A', 'B'],
            'chart_data': [50, 50]
        }
    ]
    
    try:
        pptx_buffer = generate_full_pptx_report(
            survey={'title': 'Título Extremadamente Largo ' * 5},
            analysis_data=analysis_mock,
            kpi_satisfaction_avg=8.2,
            total_responses=250,
            start_date="2024",
            end_date="2025"
        )
        with open("test_autosize.pptx", "wb") as f:
            f.write(pptx_buffer.getvalue())
        print("✓ Autosize test generated")
        
    except Exception as e:
        print(f"✗ FAILED: {e}")

if __name__ == "__main__":
    run_test()
