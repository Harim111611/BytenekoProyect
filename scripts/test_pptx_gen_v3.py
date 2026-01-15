
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
    print("Starting PPTX Generation Test V3...")
    
    # Mock Data with VERY LONG filename-like title
    survey_mock = {'title': 'gran_dataset_10k_versión_final_corregida_enero_2024_analisis_completo.csv'}
    
    analysis_mock = []
    
    try:
        # Test with explicit user name
        pdf_buffer = generate_full_pptx_report(
            survey=survey_mock,
            analysis_data=analysis_mock,
            kpi_satisfaction_avg=8.7,
            total_responses=120,
            user_name="Juan Pérez (Admin)",
            start_date="2024-01-01",
            end_date="2024-03-30",
            include_kpis=True,
            include_table=False
        )
        
        output_path = "test_output_v3.pptx"
        with open(output_path, "wb") as f:
            f.write(pdf_buffer.getvalue())
        print(f"Saved to {output_path}")
        
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_test()
