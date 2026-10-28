from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import Source


class WordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    part_of_speech: str
    translation: str
    transcription: str | None
    example: str | None


class WordSearchResult(WordRead):
    in_vocabulary: bool


class UserWordRead(BaseModel):
    word: WordRead
    added_at: datetime
    next_review_at: datetime
    interval_days: int
    repetitions: int
    ease_factor: float


class VocabularyAdd(BaseModel):
    """Либо word_id слова из общего словаря, либо своё слово: text + translation."""

    word_id: int | None = Field(default=None, gt=0)
    text: str | None = Field(default=None, min_length=1, max_length=100)
    translation: str | None = Field(default=None, min_length=1, max_length=200)
    part_of_speech: str = Field(default="other", min_length=1, max_length=30)
    example: str | None = Field(default=None, max_length=300)

    @field_validator("text", "translation", "part_of_speech", mode="before")
    @classmethod
    def strip_input(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def one_way_to_add(self) -> "VocabularyAdd":
        own_word = self.text is not None and self.translation is not None
        if (self.word_id is not None) == own_word:
            raise ValueError("Pass either word_id or both text and translation")
        return self


class AddedCount(BaseModel):
    added: int


class VocabularyPage(BaseModel):
    items: list[UserWordRead]
    total: int
    page: int
    page_size: int


class ReviewCard(BaseModel):
    """Карточка для повторения: слово + варианты перевода для режима «выбери ответ»."""

    word: WordRead
    choices: list[str]


class ReviewCreate(BaseModel):
    quality: int = Field(ge=0, le=5, description="0–2 не вспомнил, 3 с трудом, 4 хорошо, 5 легко")
    source: Source = Source.WEB


class ReviewResult(BaseModel):
    next_review_at: datetime
    interval_days: int
    repetitions: int
    ease_factor: float


class ProblemWord(BaseModel):
    word: WordRead
    failures: int
    last_failed_at: datetime
