import pytest

def test_import_pptx_generator():
    from core.reports.pptx_generator import (
        PPTXReportGenerator,
        PPTXReportBuilder,
        PPTXTheme,
        generate_full_pptx_report,
    )

    assert PPTXReportGenerator is not None
    assert PPTXReportBuilder is not None
    assert PPTXTheme is not None
    assert generate_full_pptx_report is not None


def test_generate_full_pptx_report_returns_bytesio():
    from core.reports.pptx_generator import generate_full_pptx_report

    survey = {"title": "Demo"}
    analysis_data = []
    buf = generate_full_pptx_report(survey, analysis_data, 0.0)

    assert hasattr(buf, "getvalue")
    assert len(buf.getvalue()) > 0


def test_pptx_slide_dimensions_are_widescreen():
    from core.reports.pptx_generator import PPTXReportBuilder, PPTXTheme

    builder = PPTXReportBuilder({"title": "Demo"}, [], 0.0)

    # python-pptx usa EMU internamente; comparamos por valor numérico.
    assert int(builder.prs.slide_width) == int(PPTXTheme.SLIDE_WIDTH)
    assert int(builder.prs.slide_height) == int(PPTXTheme.SLIDE_HEIGHT)
