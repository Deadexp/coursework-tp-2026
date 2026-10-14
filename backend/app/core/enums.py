import enum

from sqlalchemy import Enum


class CefrLevel(enum.StrEnum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class Source(enum.StrEnum):
    """Откуда пришло действие пользователя: сайт или Telegram-бот."""

    WEB = "web"
    BOT = "bot"


class ExerciseType(enum.StrEnum):
    MULTIPLE_CHOICE = "multiple_choice"
    FILL_GAP = "fill_gap"
    TRANSLATE = "translate"
    WORD_ORDER = "word_order"


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class PlanItemType(enum.StrEnum):
    TOPIC = "topic"
    EXERCISE = "exercise"
    WORD_REVIEW = "word_review"
    DIALOG = "dialog"


def pg_enum(enum_cls: type[enum.StrEnum], name: str) -> Enum:
    """ENUM PostgreSQL, хранящий значения ("web"), а не имена членов ("WEB")."""
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])
