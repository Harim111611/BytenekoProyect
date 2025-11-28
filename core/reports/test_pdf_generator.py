import pytest
from unittest.mock import Mock, patch
from core.reports.pdf_generator import PDFReportGenerator

class DummySurvey:
    title = "Test Survey"

def test_get_filename_returns_clean_filename():
    survey = DummySurvey()
    filename = PDFReportGenerator.get_filename(survey)
    assert filename.startswith("Reporte_Test Survey_")
    assert filename.endswith(".pdf")

@patch("core.reports.pdf_generator.HTML")
@patch("core.reports.pdf_generator.render_to_string", return_value="<html></html>")
def test_generate_report_success(mock_render, mock_html):
    survey = DummySurvey()
    analysis_data = {}
    nps_data = {"score": 80}
    mock_html.return_value.write_pdf.return_value = b"PDFDATA"
    result = PDFReportGenerator.generate_report(
        survey, analysis_data, nps_data, total_responses=10, kpi_satisfaction_avg=4.5
    )
    assert result == b"PDFDATA"
    mock_render.assert_called_once()
    mock_html.assert_called_once()

@patch("core.reports.pdf_generator.HTML", None)
def test_generate_report_raises_if_no_weasyprint():
    survey = DummySurvey()
    analysis_data = {}
    nps_data = {"score": 80}
    with pytest.raises(ValueError, match="WeasyPrint is not installed"):
        PDFReportGenerator.generate_report(
            survey, analysis_data, nps_data, total_responses=10, kpi_satisfaction_avg=4.5
        )

def test_pdf_generator_importable():
    from core import reports
    assert hasattr(reports, "pdf_generator")
    assert hasattr(reports.pdf_generator, "PDFReportGenerator")

def test_pdf_generator_instantiation():
    from core.reports.pdf_generator import PDFReportGenerator
    gen = PDFReportGenerator()
    assert isinstance(gen, PDFReportGenerator)
