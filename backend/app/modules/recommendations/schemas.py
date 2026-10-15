from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import PlanItemType


class PlanItemRead(BaseModel):
    id: int
    position: int
    type: PlanItemType
    topic_id: int | None
    title: str
    reason: str | None
    done: bool


class PlanRead(BaseModel):
    id: int
    summary: str
    created_at: datetime
    items: list[PlanItemRead]


# --- Формат, в котором отвечает модель (structured outputs) ---


class MentorStep(BaseModel):
    type: Literal["topic", "word_review", "dialog"]
    topic_id: int | None = Field(description="Topic id from the list; only for type=topic")
    reason_ru: str = Field(description="One sentence in Russian: why this step, for this learner")


class MentorPlan(BaseModel):
    summary_ru: str = Field(
        description="2-3 sentences in Russian: what the learner should focus on today and why"
    )
    steps: list[MentorStep] = Field(description="3-5 steps in the order to do them")
