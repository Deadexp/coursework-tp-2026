"""Импортирует модели всех модулей, чтобы они попали в Base.metadata (нужно Alembic)."""

from app.core.db import Base
from app.modules.dialogs.models import Dialog, DialogMessage
from app.modules.learning.models import (
    Attempt,
    ErrorType,
    Exercise,
    ExerciseAnswer,
    Mistake,
    Topic,
)
from app.modules.recommendations.models import LessonPlan, LessonPlanItem
from app.modules.users.models import TelegramLinkCode, User
from app.modules.vocabulary.models import TopicWord, UserWord, Word, WordReview

__all__ = [
    "Attempt",
    "Base",
    "Dialog",
    "DialogMessage",
    "ErrorType",
    "Exercise",
    "ExerciseAnswer",
    "LessonPlan",
    "LessonPlanItem",
    "Mistake",
    "TelegramLinkCode",
    "Topic",
    "TopicWord",
    "User",
    "UserWord",
    "Word",
    "WordReview",
    "PracticeAnswer",
    "PracticeChoice",
    "PracticeQuestion",
    "PracticeSession",
]

from app.modules.vocabulary.practice_models import (
    PracticeAnswer,
    PracticeChoice,
    PracticeQuestion,
    PracticeSession,
)
