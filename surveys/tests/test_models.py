import csv
import os
import pytest
from surveys import models
from django.contrib.auth import get_user_model

@pytest.mark.django_db
def test_import_and_delete_gran_dataset_10k():
    """Importa respuestas desde gran_dataset_10k.csv, luego elimina la encuesta y verifica cascada."""
    User = get_user_model()
    user = User.objects.create(username="testuser_csv")
    survey = models.Survey.objects.create(title="Gran Dataset 10k", description="Stress test", author=user)

    # Crear preguntas según columnas del CSV
    columns = [
        "Fecha Respuesta",
        "NPS Recomendacion",
        "Satisfaccion Soporte",
        "Edad",
        "Plan Actual",
        "Funciones Favoritas",
        "Comentarios"
    ]
    questions = [
        models.Question.objects.create(survey=survey, text=col, type="text", order=i)
        for i, col in enumerate(columns, 1)
    ]

    # Importar respuestas desde el CSV
    csv_path = os.path.join(os.path.dirname(__file__), '../../data/samples/gran_dataset_10k.csv')
    csv_path = os.path.abspath(csv_path)
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        responses = list(reader)

    # Crear una SurveyResponse y QuestionResponse por fila
    for row in responses:
        survey_response = models.SurveyResponse.objects.create(survey=survey, user=user)
        for q in questions:
            val = row.get(q.text, "")
            models.QuestionResponse.objects.create(survey_response=survey_response, question=q, text_value=val)

    assert models.SurveyResponse.objects.filter(survey=survey).count() == len(responses)
    assert models.QuestionResponse.objects.filter(question__survey=survey).count() == len(responses) * len(questions)

    survey_id = survey.id
    survey.delete()

    assert not models.Survey.objects.filter(id=survey_id).exists()
    assert not models.Question.objects.filter(survey_id=survey_id).exists()
    assert not models.SurveyResponse.objects.filter(survey_id=survey_id).exists()
    assert not models.QuestionResponse.objects.filter(question__survey_id=survey_id).exists()
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

@pytest.mark.django_db

def test_delete_survey_cascade():
    """Al eliminar una encuesta con muchos metadatos (>=10k preguntas), se eliminan en cascada."""
    User = get_user_model()
    user = User.objects.create(username="testuser3")
    survey = models.Survey.objects.create(title="Test Survey 3", description="desc", author=user)

    # Crear 10,000 preguntas (metadatos)
    questions = [
        models.Question(survey=survey, text=f"Pregunta {i}", type="text", order=i)
        for i in range(1, 10001)
    ]
    models.Question.objects.bulk_create(questions)

    # Crear una respuesta para la primera pregunta
    survey_response = models.SurveyResponse.objects.create(survey=survey, user=user)
    question_response = models.QuestionResponse.objects.create(
        survey_response=survey_response, question=questions[0], text_value="Azul"
    )

    assert models.Question.objects.filter(survey=survey).count() == 10000

    survey_id = survey.id

    # Eliminar la encuesta
    survey.delete()

    assert not models.Survey.objects.filter(id=survey_id).exists()
    assert not models.Question.objects.filter(survey_id=survey_id).exists()
    assert not models.SurveyResponse.objects.filter(id=survey_response.id).exists()
    assert not models.QuestionResponse.objects.filter(id=question_response.id).exists()
