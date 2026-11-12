"""Независимые от грамматического курса тематические наборы слов."""

from sqlalchemy import CheckConstraint, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, IntPK
from app.core.enums import CefrLevel, pg_enum


class VocabularyModule(Base):
    __tablename__ = "vocabulary_modules"
    __table_args__ = (CheckConstraint("position > 0", name="positive_position"),)

    id: Mapped[IntPK]
    slug: Mapped[str] = mapped_column(unique=True)
    title: Mapped[str]
    description: Mapped[str]
    cefr_level: Mapped[CefrLevel] = mapped_column(pg_enum(CefrLevel, "cefr_level"))
    position: Mapped[int] = mapped_column(Integer, unique=True)


class ModuleWord(Base):
    __tablename__ = "module_words"
    __table_args__ = (
        UniqueConstraint("module_id", "position"),
        CheckConstraint("position > 0", name="positive_position"),
    )

    module_id: Mapped[int] = mapped_column(
        ForeignKey("vocabulary_modules.id", ondelete="CASCADE"), primary_key=True
    )
    word_id: Mapped[int] = mapped_column(
        ForeignKey("words.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer)
