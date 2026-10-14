from datetime import datetime

from sqlalchemy import (
    REAL,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IntPK
from app.core.enums import Source, pg_enum


class Word(Base):
    """Общий словарь. Одно слово с разными значениями — разные строки."""

    __tablename__ = "words"
    __table_args__ = (UniqueConstraint("text", "part_of_speech", "translation"),)

    id: Mapped[IntPK]
    text: Mapped[str]
    part_of_speech: Mapped[str]
    translation: Mapped[str]
    transcription: Mapped[str | None]
    example: Mapped[str | None]


class TopicWord(Base):
    __tablename__ = "topic_words"

    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    word_id: Mapped[int] = mapped_column(
        ForeignKey("words.id", ondelete="CASCADE"), primary_key=True
    )


class UserWord(Base):
    """Личный словарь + состояние алгоритма интервального повторения SM-2."""

    __tablename__ = "user_words"
    __table_args__ = (
        CheckConstraint("ease_factor >= 1.3", name="ease_factor_min"),
        CheckConstraint("interval_days >= 0 AND repetitions >= 0", name="sm2_non_negative"),
        Index("ix_user_words_user_id_next_review_at", "user_id", "next_review_at"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    word_id: Mapped[int] = mapped_column(
        ForeignKey("words.id", ondelete="CASCADE"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ease_factor: Mapped[float] = mapped_column(REAL, server_default="2.5")
    interval_days: Mapped[int] = mapped_column(Integer, server_default="0")
    repetitions: Mapped[int] = mapped_column(Integer, server_default="0")
    next_review_at: Mapped[datetime] = mapped_column(server_default=func.now())


class WordReview(Base):
    __tablename__ = "word_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "word_id"],
            ["user_words.user_id", "user_words.word_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("quality BETWEEN 0 AND 5", name="quality_range"),
        Index("ix_word_reviews_user_id_word_id", "user_id", "word_id"),
    )

    id: Mapped[IntPK]
    user_id: Mapped[int]
    word_id: Mapped[int]
    quality: Mapped[int] = mapped_column(SmallInteger)
    source: Mapped[Source] = mapped_column(pg_enum(Source, "source"))
    reviewed_at: Mapped[datetime] = mapped_column(server_default=func.now())
