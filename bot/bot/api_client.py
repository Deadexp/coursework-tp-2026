"""The connected bot uses only the backend, never a database or a demo fallback."""

from datetime import datetime
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError, model_validator


class BackendError(Exception):
    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(f"Backend request failed ({status})")


class Word(BaseModel):
    id: int
    text: str
    translation: str


class UserWord(BaseModel):
    word: Word
    next_review_at: datetime


class VocabularyPage(BaseModel):
    items: list[UserWord]
    total: int = Field(ge=0)
    page: int = Field(ge=0)
    page_size: int = Field(ge=1)


class LinkedUser(BaseModel):
    display_name: str


class ReviewResult(BaseModel):
    next_review_at: datetime
    interval_days: int


class PracticeQuestion(BaseModel):
    position: int
    kind: Literal["card", "choice", "recall"]
    prompt: str
    choices: list[str] = Field(default_factory=list)
    revealed: bool = False
    translation: str | None = None


class PracticeState(BaseModel):
    session_id: int
    mode: str
    completed: bool
    total: int
    answered: int
    cards_reviewed: int
    attempted: int
    correct: int
    question: PracticeQuestion | None = None

    @model_validator(mode="after")
    def current_question_required(self):
        if not self.completed and self.question is None:
            raise ValueError("Current question is missing")
        if self.question and self.question.revealed and self.question.translation is None:
            raise ValueError("Revealed translation is missing")
        return self


class PracticeFeedback(BaseModel):
    is_correct: bool | None
    word: str
    translation: str
    next_review_at: datetime
    state: PracticeState


class Progress(BaseModel):
    level: str
    words: int
    due: int
    reviews: int
    attempted: int
    correct: int
    quizzes_completed: int
    daily_completed: int
    grammar_attempted: int = 0
    grammar_correct: int = 0
    last_daily_date: str | None = None


class GrammarTopic(BaseModel):
    id: int
    title: str
    exercises_total: int


class GrammarQuestion(BaseModel):
    position: int
    topic: str
    type: Literal["multiple_choice", "fill_gap", "translate", "word_order"]
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

    @model_validator(mode="after")
    def current_question_required(self):
        if not self.completed and self.question is None:
            raise ValueError("Current grammar question is missing")
        return self


class GrammarFeedback(BaseModel):
    is_correct: bool
    correct_answers: list[str]
    explanation: str | None
    state: GrammarState


class BackendClient:
    def __init__(
        self,
        base_url: str,
        service_token: str,
        *,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.http = http or httpx.AsyncClient(base_url=base_url, timeout=15)
        self.service_token = service_token
        self.owns_http = http is None

    async def aclose(self) -> None:
        if self.owns_http:
            await self.http.aclose()

    async def _request(self, method: str, path: str, sender: int, **kwargs):
        try:
            response = await self.http.request(
                method,
                path,
                headers={
                    "X-Service-Token": self.service_token,
                    "X-Telegram-ID": str(sender),
                },
                **kwargs,
            )
        except httpx.RequestError:
            # Never expose exceptions containing request data, URLs or credentials.
            raise BackendError(0) from None
        if response.is_error:
            raise BackendError(response.status_code)
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError:
            raise BackendError(502) from None

    async def me(self, sender: int) -> str:
        result = await self._request("GET", "/telegram/me", sender)
        return self._display_name(result)

    async def link(self, sender: int, code: str) -> str:
        result = await self._request(
            "POST",
            "/telegram/link",
            sender,
            json={
                "code": code,
                "telegram_id": sender,
            },
        )
        return self._display_name(result)

    @staticmethod
    def _display_name(result) -> str:
        try:
            return LinkedUser.model_validate(result).display_name
        except ValidationError:
            raise BackendError(502) from None

    async def dictionary(self, sender: int, page: int = 0) -> VocabularyPage:
        result = await self._request("GET", "/vocabulary/page", sender, params={"page": page})
        try:
            return VocabularyPage.model_validate(result)
        except ValidationError:
            raise BackendError(502) from None

    async def add_word(self, sender: int, text: str, translation: str) -> None:
        await self._request(
            "POST",
            "/vocabulary",
            sender,
            json={
                "text": text,
                "translation": translation,
            },
        )

    async def remove_word(self, sender: int, word_id: int) -> None:
        await self._request("DELETE", f"/vocabulary/{word_id}", sender)

    async def cards(self, sender: int, *, difficult: bool = False) -> list[Word]:
        path = "/vocabulary/problem-words" if difficult else "/vocabulary/review"
        result = await self._request("GET", path, sender, params={"limit": 20})
        try:
            return [Word.model_validate(row["word"]) for row in result]
        except (ValidationError, KeyError, TypeError):
            raise BackendError(502) from None

    async def review(self, sender: int, word_id: int, quality: int) -> ReviewResult:
        result = await self._request(
            "POST",
            f"/vocabulary/{word_id}/reviews",
            sender,
            json={
                "quality": quality,
                "source": "bot",
            },
        )
        try:
            return ReviewResult.model_validate(result)
        except ValidationError:
            raise BackendError(502) from None

    async def start_practice(self, sender: int, mode: str) -> PracticeState:
        result = await self._request("POST", "/practice/sessions", sender, json={"mode": mode})
        return self._validated(PracticeState, result)

    async def reveal_practice(self, sender: int, session_id: int, position: int) -> PracticeState:
        result = await self._request(
            "POST", f"/practice/sessions/{session_id}/reveal", sender, json={"position": position}
        )
        return self._validated(PracticeState, result)

    async def answer_practice(
        self, sender: int, session_id: int, position: int, **answer
    ) -> PracticeFeedback:
        result = await self._request(
            "POST",
            f"/practice/sessions/{session_id}/answers",
            sender,
            json={"position": position, **answer},
        )
        return self._validated(PracticeFeedback, result)

    async def progress(self, sender: int) -> Progress:
        return self._validated(Progress, await self._request("GET", "/practice/progress", sender))

    async def level(self, sender: int, level: str | None = None) -> str:
        result = await self._request(
            "GET" if level is None else "PATCH",
            "/practice/level",
            sender,
            **({} if level is None else {"json": {"level": level}}),
        )
        if not isinstance(result, dict) or result.get("level") not in (
            "A1",
            "A2",
            "B1",
            "B2",
            "C1",
            "C2",
        ):
            raise BackendError(502)
        return result["level"]

    @staticmethod
    def _validated(schema, result):
        try:
            return schema.model_validate(result)
        except ValidationError:
            raise BackendError(502) from None

    async def grammar_topics(self, sender: int) -> list[GrammarTopic]:
        result = await self._request("GET", "/grammar/topics", sender)
        if not isinstance(result, list):
            raise BackendError(502)
        return [self._validated(GrammarTopic, row) for row in result]

    async def start_grammar(
        self,
        sender: int,
        topic_id: int | None,
        previous_token: str | None = None,
    ) -> GrammarState:
        result = await self._request(
            "POST",
            "/grammar/quizzes",
            sender,
            json={
                "topic_id": topic_id,
                "previous_token": previous_token,
            },
        )
        return self._validated(GrammarState, result)

    async def answer_grammar(
        self,
        sender: int,
        session_token: str,
        position: int,
        **answer,
    ) -> GrammarFeedback:
        result = await self._request(
            "POST",
            "/grammar/quizzes/answers",
            sender,
            json={
                "session_token": session_token,
                "position": position,
                **answer,
            },
        )
        return self._validated(GrammarFeedback, result)
