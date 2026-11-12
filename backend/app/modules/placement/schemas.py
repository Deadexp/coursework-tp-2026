from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PlacementLevel = Literal["A1", "A2", "B1"]
PlacementSkill = Literal["grammar", "vocabulary", "reading"]


class QuestionRead(BaseModel):
    id: str
    position: int
    level: PlacementLevel
    skill: PlacementSkill
    prompt: str
    passage: str | None
    options: list[str]


class AnswerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=50)
    option_index: int = Field(ge=0, le=3, strict=True)


class SubmitInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[AnswerInput] = Field(min_length=24, max_length=24)

    @model_validator(mode="after")
    def unique_questions(self) -> "SubmitInput":
        ids = [answer.question_id for answer in self.answers]
        if len(ids) != len(set(ids)):
            raise ValueError("Ответьте на каждый вопрос ровно один раз.")
        return self


class LevelScore(BaseModel):
    level: PlacementLevel
    correct: int
    total: int


class AnswerFeedback(BaseModel):
    question_id: str
    option_index: int
    correct_option_index: int
    is_correct: bool
    explanation: str


class PlacementResult(BaseModel):
    recommended_level: PlacementLevel
    correct: int
    total: int
    scores: list[LevelScore]
    summary: str
    limitations: str
    answers: list[AnswerFeedback]


class AttemptRead(BaseModel):
    id: int
    version: str
    status: Literal["in_progress", "completed"]
    started_at: datetime
    submitted_at: datetime | None
    applied_at: datetime | None
    total: int
    questions: list[QuestionRead]
    result: PlacementResult | None
