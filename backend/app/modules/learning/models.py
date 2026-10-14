from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, IntPK
from app.core.enums import CefrLevel, ExerciseType, Source, pg_enum


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[IntPK]
    title: Mapped[str] = mapped_column(unique=True)
    theory: Mapped[str]
    cefr_level: Mapped[CefrLevel] = mapped_column(pg_enum(CefrLevel, "cefr_level"))
    position: Mapped[int] = mapped_column(Integer, unique=True)


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[IntPK]
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    type: Mapped[ExerciseType] = mapped_column(pg_enum(ExerciseType, "exercise_type"))
    prompt: Mapped[str]
    explanation: Mapped[str | None]


class ExerciseAnswer(Base):
    """Для выбора — показываемые варианты; для ввода — все принимаемые верные ответы."""

    __tablename__ = "exercise_answers"

    id: Mapped[IntPK]
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str]
    is_correct: Mapped[bool]


class ErrorType(Base):
    __tablename__ = "error_types"

    id: Mapped[IntPK]
    code: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"))


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (Index("ix_attempts_user_id_created_at", "user_id", "created_at"),)

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    answer: Mapped[str]
    is_correct: Mapped[bool]
    source: Mapped[Source] = mapped_column(pg_enum(Source, "source"))
    created_at: Mapped[CreatedAt]


class Mistake(Base):
    """Ошибка из упражнения или из диалога — ровно один из двух источников."""

    __tablename__ = "mistakes"
    __table_args__ = (
        CheckConstraint("num_nonnulls(attempt_id, dialog_message_id) = 1", name="one_source"),
    )

    id: Mapped[IntPK]
    attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("attempts.id", ondelete="CASCADE"), index=True
    )
    dialog_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("dialog_messages.id", ondelete="CASCADE"), index=True
    )
    error_type_id: Mapped[int] = mapped_column(ForeignKey("error_types.id"), index=True)
    fragment: Mapped[str]
    correction: Mapped[str]
    explanation: Mapped[str | None]
