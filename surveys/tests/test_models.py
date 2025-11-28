import pytest
from surveys import models
from django.contrib.auth import get_user_model

@pytest.mark.django_db
def test_create_survey_and_question():
    User = get_user_model()
    user = User.objects.create(username="testuser1")
    survey = models.Survey.objects.create(title="Test Survey", description="desc", author=user)
    question = models.Question.objects.create(survey=survey, text="How are you?", type="text", order=1)
    assert models.Survey.objects.count() == 1
    assert models.Question.objects.count() == 1
    assert question.survey == survey

@pytest.mark.django_db
def test_create_survey_response_and_question_response():
    User = get_user_model()
    user = User.objects.create(username="testuser2")
    survey = models.Survey.objects.create(title="Test Survey 2", description="desc", author=user)
    question = models.Question.objects.create(survey=survey, text="How old are you?", type="number", order=1)
    survey_response = models.SurveyResponse.objects.create(survey=survey, user=user)
    question_response = models.QuestionResponse.objects.create(
        survey_response=survey_response, question=question, text_value="25"
    )
    assert models.SurveyResponse.objects.count() == 1
    assert models.QuestionResponse.objects.count() == 1
    assert question_response.survey_response == survey_response
    assert question_response.question == question
    assert question_response.text_value == "25"
