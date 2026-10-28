from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import CefrLevel


class StartPractice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["quiz", "daily"]


class QuestionPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: int = Field(ge=0, le=4, strict=True)


class AnswerInput(QuestionPosition):
    answer: str | None = Field(default=None, min_length=1, max_length=200)
    option_index: int | None = Field(default=None, ge=0, le=3, strict=True)
    quality: Literal[1, 3, 4, 5] | None = None

    @field_validator("answer", mode="before")
    @classmethod
    def strip_answer(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def exactly_one_answer(self):
        if sum(v is not None for v in [self.answer, self.option_index, self.quality]) != 1:
            raise ValueError("Pass exactly one answer, option_index or quality")
        return self


class QuestionView(BaseModel):
    position: int
    kind: Literal["card", "choice", "recall"]
    prompt: str
    choices: list[str] = []
    revealed: bool = False
    translation: str | None = None


class PracticeState(BaseModel):
    session_id: int
    mode: Literal["quiz", "daily"]
    practice_date: date | None
    completed: bool
    total: int
    answered: int
    cards_reviewed: int
    attempted: int
    correct: int
    question: QuestionView | None


class AnswerResult(BaseModel):
    is_correct: bool | None
    word: str
    translation: str
    next_review_at: datetime
    state: PracticeState


class ProgressRead(BaseModel):
    level: CefrLevel
    words: int
    due: int
    reviews: int
    attempted: int
    correct: int
    quizzes_completed: int
    daily_completed: int
    grammar_attempted: int = 0
    grammar_correct: int = 0
    last_daily_date: date | None


class LevelRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: CefrLevel
