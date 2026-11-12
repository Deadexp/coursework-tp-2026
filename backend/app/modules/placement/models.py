from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, IntPK


class PlacementAttempt(Base):
    __tablename__ = "placement_attempts"
    __table_args__ = (
        CheckConstraint("pass_mark BETWEEN 1 AND 8", name="pass_mark_range"),
        CheckConstraint(
            "applied_at IS NULL OR submitted_at IS NOT NULL", name="apply_requires_submission"
        ),
        Index("ix_placement_attempts_user_id_started_at", "user_id", "started_at"),
    )

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    version: Mapped[str]
    pass_mark: Mapped[int] = mapped_column(SmallInteger)
    started_at: Mapped[CreatedAt]
    submitted_at: Mapped[datetime | None]
    applied_at: Mapped[datetime | None]


class PlacementQuestion(Base):
    """Immutable assigned content: old attempts survive changes to the question bank."""

    __tablename__ = "placement_questions"
    __table_args__ = (
        UniqueConstraint("attempt_id", "code"),
        UniqueConstraint("attempt_id", "position"),
        CheckConstraint("position BETWEEN 1 AND 24", name="position_range"),
        CheckConstraint("level IN ('A1', 'A2', 'B1')", name="level_allowed"),
        CheckConstraint("skill IN ('grammar', 'vocabulary', 'reading')", name="skill_allowed"),
    )

    id: Mapped[IntPK]
    attempt_id: Mapped[int] = mapped_column(ForeignKey("placement_attempts.id", ondelete="CASCADE"))
    code: Mapped[str]
    position: Mapped[int] = mapped_column(SmallInteger)
    level: Mapped[str]
    skill: Mapped[str]
    prompt: Mapped[str]
    passage: Mapped[str | None]
    explanation: Mapped[str]


class PlacementOption(Base):
    __tablename__ = "placement_options"
    __table_args__ = (
        CheckConstraint("position BETWEEN 0 AND 3", name="position_range"),
        Index(
            "uq_placement_options_correct",
            "question_id",
            unique=True,
            postgresql_where=text("is_correct"),
        ),
    )

    question_id: Mapped[int] = mapped_column(
        ForeignKey("placement_questions.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    text: Mapped[str]
    is_correct: Mapped[bool]


class PlacementAnswer(Base):
    __tablename__ = "placement_answers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["question_id", "option_index"],
            ["placement_options.question_id", "placement_options.position"],
            ondelete="CASCADE",
        ),
    )

    question_id: Mapped[int] = mapped_column(primary_key=True)
    option_index: Mapped[int] = mapped_column(SmallInteger)
