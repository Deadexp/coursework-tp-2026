"""Тематические модули словаря и локальные иллюстрации.

Revision ID: a26111200003
Revises: a26111200002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a26111200003"
down_revision: str | None = "a26111200002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("words", sa.Column("image_url", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_words_local_image_url"),
        "words",
        r"image_url IS NULL OR image_url ~ '^/images/vocabulary/[a-z0-9][a-z0-9-]*\.svg$'",
    )
    op.create_table(
        "vocabulary_modules",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "cefr_level",
            postgresql.ENUM(
                "A1", "A2", "B1", "B2", "C1", "C2", name="cefr_level", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("position > 0", name=op.f("ck_vocabulary_modules_positive_position")),
        sa.PrimaryKeyConstraint("id", name="pk_vocabulary_modules"),
        sa.UniqueConstraint("slug", name="uq_vocabulary_modules_slug"),
        sa.UniqueConstraint("position", name="uq_vocabulary_modules_position"),
    )
    op.create_table(
        "module_words",
        sa.Column("module_id", sa.BigInteger(), nullable=False),
        sa.Column("word_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("position > 0", name=op.f("ck_module_words_positive_position")),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["vocabulary_modules.id"],
            name="fk_module_words_module_id_vocabulary_modules",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["word_id"],
            ["words.id"],
            name="fk_module_words_word_id_words",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("module_id", "word_id", name="pk_module_words"),
        sa.UniqueConstraint("module_id", "position", name="uq_module_words_module_id_position"),
    )
    op.create_index("ix_module_words_word_id", "module_words", ["word_id"])


def downgrade() -> None:
    op.drop_index("ix_module_words_word_id", table_name="module_words")
    op.drop_table("module_words")
    op.drop_table("vocabulary_modules")
    op.drop_constraint(op.f("ck_words_local_image_url"), "words", type_="check")
    op.drop_column("words", "image_url")
    # cefr_level belongs to the pre-existing course schema and is retained.
