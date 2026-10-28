"""Persistent practice sessions. Scores are computed from answers, never cached."""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, SmallInteger, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, IntPK


class PracticeSession(Base):
    __tablename__ = "practice_sessions"
    __table_args__ = (
        CheckConstraint("mode IN ('quiz', 'daily')", name="practice_mode"),
        CheckConstraint(
            "(mode = 'daily' AND practice_date IS NOT NULL) OR "
            "(mode = 'quiz' AND practice_date IS NULL)",
            name="practice_day_by_mode",
        ),
        CheckConstraint(
            "completed_at IS NULL OR cancelled_at IS NULL",
            name="practice_final_state",
        ),
        Index(
            "uq_practice_daily_active",
            "user_id",
            "practice_date",
            unique=True,
            postgresql_where=text("mode = 'daily' AND cancelled_at IS NULL"),
        ),
    )

    id: Mapped[IntPK]
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str]
    practice_date: Mapped[date | None]
    created_at: Mapped[CreatedAt]
    completed_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]


class PracticeQuestion(Base):
    __tablename__ = "practice_questions"
    __table_args__ = (
        CheckConstraint("position BETWEEN 0 AND 4", name="practice_position"),
        CheckConstraint("kind IN ('card', 'choice', 'recall')", name="practice_question_kind"),
        CheckConstraint("kind = 'card' OR revealed_at IS NULL", name="practice_reveal_card"),
    )

    session_id: Mapped[int] = mapped_column(
        ForeignKey("practice_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str]
    gap_prompt: Mapped[str | None]
    revealed_at: Mapped[datetime | None]


class PracticeChoice(Base):
    __tablename__ = "practice_choices"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "position"],
            ["practice_questions.session_id", "practice_questions.position"],
            ondelete="CASCADE",
        ),
        CheckConstraint("choice_index BETWEEN 0 AND 3", name="practice_choice_index"),
    )

    session_id: Mapped[int] = mapped_column(primary_key=True)
    position: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    choice_index: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id", ondelete="RESTRICT"))


class PracticeAnswer(Base):
    __tablename__ = "practice_answers"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "position"],
            ["practice_questions.session_id", "practice_questions.position"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["session_id", "position", "option_index"],
            [
                "practice_choices.session_id",
                "practice_choices.position",
                "practice_choices.choice_index",
            ],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "num_nonnulls(answer, option_index, quality) = 1", name="practice_one_answer"
        ),
        CheckConstraint("quality IS NULL OR quality IN (1,3,4,5)", name="practice_quality"),
        CheckConstraint(
            "(quality IS NULL) = (is_correct IS NOT NULL)",
            name="practice_objective_score",
        ),
    )

    session_id: Mapped[int] = mapped_column(primary_key=True)
    position: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    answer: Mapped[str | None]
    option_index: Mapped[int | None] = mapped_column(SmallInteger)
    quality: Mapped[int | None] = mapped_column(SmallInteger)
    is_correct: Mapped[bool | None]
    next_review_at: Mapped[datetime]  # Historical server receipt, not the current SM-2 state.
    created_at: Mapped[CreatedAt]
