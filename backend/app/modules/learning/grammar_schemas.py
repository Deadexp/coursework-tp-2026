from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import ExerciseType


class QuizStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic_id: int | None = Field(default=None, gt=0, strict=True)
    previous_token: str | None = Field(default=None, max_length=4096)


class QuizAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_token: str = Field(min_length=1, max_length=4096)
    position: int = Field(ge=0, le=4, strict=True)
    answer: str | None = Field(default=None, min_length=1, max_length=500)
    option_index: int | None = Field(default=None, ge=0, le=99, strict=True)

    @field_validator("answer", mode="before")
    @classmethod
    def trim_answer(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def single_answer(self):
        if (self.answer is None) == (self.option_index is None):
            raise ValueError("Send exactly one text answer or option_index")
        return self


class GrammarQuestion(BaseModel):
    position: int
    topic: str
    type: ExerciseType
    prompt: str
    options: list[str] = Field(default_factory=list)
    words: list[str] = Field(default_factory=list)


class GrammarState(BaseModel):
    session_token: str
    topic_id: int | None
    total: int
    answered: int
    correct: int
    completed: bool
    mistake_topics: list[str]
    question: GrammarQuestion | None


class GrammarFeedback(BaseModel):
    is_correct: bool
    correct_answers: list[str]
    explanation: str | None
    state: GrammarState
