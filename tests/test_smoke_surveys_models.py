import pytest
import importlib

def test_surveys_models_importable():
    models = importlib.import_module("surveys.models")
    assert hasattr(models, "Survey")
    assert hasattr(models, "Question")
    assert hasattr(models, "SurveyResponse")
    assert hasattr(models, "QuestionResponse")

def test_surveys_admin_importable():
    admin = importlib.import_module("surveys.admin")
    assert admin is not None
