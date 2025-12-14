import pytest
from core.services import survey_analysis

def test_get_analysis_data_smoke():
    # This is a smoke test to ensure the function is importable and callable
    assert hasattr(survey_analysis.SurveyAnalysisService, "get_analysis_data")
