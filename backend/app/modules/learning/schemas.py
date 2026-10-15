from pydantic import BaseModel, Field

from app.core.enums import CefrLevel, ExerciseType, Source


class TopicSummary(BaseModel):
    id: int
    title: str
    cefr_level: CefrLevel
    position: int
    exercises_total: int
    exercises_solved: int


class ExerciseRead(BaseModel):
    """Упражнение без правильных ответов — их клиент узнаёт только после попытки."""

    id: int
    type: ExerciseType
    prompt: str
    options: list[str] | None = None  # multiple_choice
    words: list[str] | None = None  # word_order: перемешанные слова
    solved: bool = False  # пользователь хотя бы раз ответил верно


class TopicDetail(BaseModel):
    id: int
    title: str
    cefr_level: CefrLevel
    theory: str
    exercises: list[ExerciseRead]


class AttemptCreate(BaseModel):
    answer: str = Field(min_length=1, max_length=500)
    source: Source = Source.WEB


class ErrorTypeRead(BaseModel):
    code: str
    name: str


class AttemptResult(BaseModel):
    is_correct: bool
    correct_answers: list[str]
    explanation: str | None
    error_type: ErrorTypeRead | None = None
