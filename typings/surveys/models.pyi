from __future__ import annotations

from typing import Any, Optional, Sequence, Tuple

from django.contrib.auth.models import User
from django.db import models
from django.db.models.manager import RelatedManager


class Survey(models.Model):
    STATUS_DRAFT: str
    STATUS_ACTIVE: str
    STATUS_PAUSED: str
    STATUS_CLOSED: str

    STATUS_CHOICES: Sequence[Tuple[str, str]]

    id: int
    title: str
    description: Optional[str]
    category: str
    status: str
    author: User
    author_id: int
    author_sequence: Optional[int]
    public_id: Optional[str]
    sample_goal: int
    is_imported: bool
    created_at: Any
    updated_at: Any

    questions: RelatedManager[Question]
    responses: RelatedManager[SurveyResponse]

    # Used in views; often computed (annotation/property)
    response_count: int

    def get_status_display(self) -> str: ...


class Question(models.Model):
    id: int
    survey: Survey
    survey_id: int
    text: str
    type: str
    is_required: bool
    order: int


class SurveyResponse(models.Model):
    id: int
    survey: Survey
    survey_id: int
    user: Optional[User]
    user_id: Optional[int]
    created_at: Any
    is_anonymous: bool


class QuestionResponse(models.Model):
    id: int
    survey_response: SurveyResponse
    survey_response_id: int
    question: Question
    question_id: int
    selected_option: Any
    text_value: Optional[str]
    numeric_value: Optional[int]
