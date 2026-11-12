"""Persist assigned placement diagnostics and answers.

Revision ID: a26111200001
Revises: 43519f5b65f9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a26111200001"
down_revision: str | Sequence[str] | None = "43519f5b65f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "placement_attempts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("pass_mark", sa.SmallInteger(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "pass_mark BETWEEN 1 AND 8", name=op.f("ck_placement_attempts_pass_mark_range")
        ),
        sa.CheckConstraint(
            "applied_at IS NULL OR submitted_at IS NOT NULL",
            name=op.f("ck_placement_attempts_apply_requires_submission"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_placement_attempts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_placement_attempts")),
    )
    op.create_index(
        "ix_placement_attempts_user_id_started_at", "placement_attempts", ["user_id", "started_at"]
    )
    op.create_table(
        "placement_questions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("attempt_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("skill", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("passage", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "position BETWEEN 1 AND 24", name=op.f("ck_placement_questions_position_range")
        ),
        sa.CheckConstraint(
            "level IN ('A1', 'A2', 'B1')", name=op.f("ck_placement_questions_level_allowed")
        ),
        sa.CheckConstraint(
            "skill IN ('grammar', 'vocabulary', 'reading')",
            name=op.f("ck_placement_questions_skill_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["placement_attempts.id"],
            name=op.f("fk_placement_questions_attempt_id_placement_attempts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_placement_questions")),
        sa.UniqueConstraint(
            "attempt_id", "code", name=op.f("uq_placement_questions_attempt_id_code")
        ),
        sa.UniqueConstraint(
            "attempt_id", "position", name=op.f("uq_placement_questions_attempt_id_position")
        ),
    )
    op.create_table(
        "placement_options",
        sa.Column("question_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "position BETWEEN 0 AND 3", name=op.f("ck_placement_options_position_range")
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["placement_questions.id"],
            name=op.f("fk_placement_options_question_id_placement_questions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("question_id", "position", name=op.f("pk_placement_options")),
    )
    op.create_index(
        "uq_placement_options_correct",
        "placement_options",
        ["question_id"],
        unique=True,
        postgresql_where=sa.text("is_correct"),
    )
    op.create_table(
        "placement_answers",
        sa.Column("question_id", sa.BigInteger(), nullable=False),
        sa.Column("option_index", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id", "option_index"],
            ["placement_options.question_id", "placement_options.position"],
            name=op.f("fk_placement_answers_question_id_placement_options"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("question_id", name=op.f("pk_placement_answers")),
    )


def downgrade() -> None:
    op.drop_table("placement_answers")
    op.drop_index("uq_placement_options_correct", table_name="placement_options")
    op.drop_table("placement_options")
    op.drop_table("placement_questions")
    op.drop_index("ix_placement_attempts_user_id_started_at", table_name="placement_attempts")
    op.drop_table("placement_attempts")
