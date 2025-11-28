import pytest
from django.contrib import admin
from surveys import admin as surveys_admin
from surveys import models


def test_admin_site_registration():
    # Check that Survey, Question, SurveyResponse, QuestionResponse are registered
    registered = admin.site._registry
    assert models.Survey in registered
    assert models.Question in registered
    assert models.SurveyResponse in registered
    assert models.QuestionResponse in registered
