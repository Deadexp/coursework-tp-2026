from collections import Counter
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.placement.schemas import PlacementLevel, PlacementSkill

CONTENT_FILE = Path(__file__).resolve().parents[3] / "content" / "placement.json"


class QuestionContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=50)
    position: int = Field(ge=1, le=24)
    level: PlacementLevel
    skill: PlacementSkill
    prompt: str = Field(min_length=1)
    passage: str | None = None
    options: list[str] = Field(min_length=4, max_length=4)
    correct_option_index: int = Field(ge=0, le=3, strict=True)
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_options(self) -> "QuestionContent":
        normalized = [option.strip().casefold() for option in self.options]
        if not all(normalized) or len(set(normalized)) != 4:
            raise ValueError("Question options must be nonempty and distinct")
        if self.skill == "reading" and not self.passage:
            raise ValueError("Reading questions must include a passage")
        return self


class PlacementContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=50)
    pass_mark: int = Field(ge=1, le=8, strict=True)
    questions: list[QuestionContent] = Field(min_length=24, max_length=24)

    @model_validator(mode="after")
    def balanced_test(self) -> "PlacementContent":
        if len({q.id for q in self.questions}) != 24:
            raise ValueError("Question identifiers must be unique")
        if sorted(q.position for q in self.questions) != list(range(1, 25)):
            raise ValueError("Question positions must be 1 through 24")
        if Counter(q.level for q in self.questions) != {"A1": 8, "A2": 8, "B1": 8}:
            raise ValueError("The diagnostic must contain eight questions at each level")
        for level in ("A1", "A2", "B1"):
            skills = Counter(q.skill for q in self.questions if q.level == level)
            if skills != {"grammar": 4, "vocabulary": 2, "reading": 2}:
                raise ValueError("Each level needs four grammar, two vocabulary, two reading items")
        return self


@lru_cache(maxsize=1)
def load_content() -> PlacementContent:
    return PlacementContent.model_validate_json(CONTENT_FILE.read_text(encoding="utf-8"))
