from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import MessageRole
from app.modules.learning.schemas import ErrorTypeRead


class ScenarioRead(BaseModel):
    code: str
    title: str
    description: str


class DialogCreate(BaseModel):
    scenario: str


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class CorrectionRead(BaseModel):
    fragment: str
    correction: str
    explanation: str | None
    error_type: ErrorTypeRead


class DialogMessageRead(BaseModel):
    id: int
    role: MessageRole
    content: str
    created_at: datetime
    corrections: list[CorrectionRead] = []


class DialogSummaryRead(BaseModel):
    id: int
    scenario: str
    title: str
    started_at: datetime
    ended_at: datetime | None
    messages: int


class DialogRead(BaseModel):
    id: int
    scenario: str
    title: str
    started_at: datetime
    ended_at: datetime | None
    summary: str | None
    messages: list[DialogMessageRead]


class ExchangeResult(BaseModel):
    """Ответ на реплику ученика: его сообщение с исправлениями и ответ собеседника."""

    user_message: DialogMessageRead
    reply: DialogMessageRead


# --- Формат, в котором отвечает модель (structured outputs) ---


class SpeakerCorrection(BaseModel):
    fragment: str = Field(description="Exact words from the learner's message that are wrong")
    correction: str = Field(description="The corrected version of the fragment")
    explanation_ru: str = Field(description="One short sentence in Russian explaining the rule")
    error_type: str = Field(description="Closest error type code from the provided list")


class SpeakerTurn(BaseModel):
    corrections: list[SpeakerCorrection]
    reply: str = Field(description="Your next line in the conversation, in English")


class DialogFeedback(BaseModel):
    summary_ru: str = Field(description="2-3 sentences in Russian: how the conversation went")
    strengths_ru: list[str] = Field(description="1-3 things the learner did well, in Russian")
    to_improve_ru: list[str] = Field(description="1-3 concrete things to work on, in Russian")
