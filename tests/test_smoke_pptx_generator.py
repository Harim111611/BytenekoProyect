import pytest

# Smoke test for import and instantiation

def test_import_pptx_generator():
    from core.reports.pptx_generator import PPTXReportGenerator, PPTXSlideBuilder, PPTXStyleConfig
    assert PPTXReportGenerator is not None
    assert PPTXSlideBuilder is not None
    assert PPTXStyleConfig is not None

# Test instantiation of PPTXSlideBuilder with a dummy presentation

def test_pptx_slide_builder_instantiation():
    from pptx import Presentation
    from core.reports.pptx_generator import PPTXSlideBuilder
    prs = Presentation()
    builder = PPTXSlideBuilder(prs)
    assert builder.prs is prs

# Test static methods with minimal input

def test_clean_title_basic():
    from core.reports.pptx_generator import PPTXReportGenerator
    assert PPTXReportGenerator._clean_title("Test Title") == "Test Title"


def test_split_question_title_basic():
    from core.reports.pptx_generator import PPTXReportGenerator
    base, extra = PPTXReportGenerator._split_question_title("Question (extra)")
    assert base == "Question"
    assert extra == "(extra)"


def test_is_text_like_question_text():
    from core.reports.pptx_generator import PPTXReportGenerator
    item = {"type": "text", "text": "Comentario"}
    assert PPTXReportGenerator._is_text_like_question(item)


def test_is_text_like_question_non_text():
    from core.reports.pptx_generator import PPTXReportGenerator
    item = {"type": "number", "text": "Puntaje"}
    assert not PPTXReportGenerator._is_text_like_question(item)
