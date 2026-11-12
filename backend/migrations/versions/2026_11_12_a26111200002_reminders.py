"""Opt-in Telegram reminder settings and leased daily deliveries.

Revision ID: a26111200002
Revises: a26111200001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a26111200002"
down_revision: str | Sequence[str] | None = "a26111200001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reminder_settings",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("delivery_time", sa.Time(), server_default="19:00:00", nullable=False),
        sa.Column("timezone", sa.Text(), server_default="Europe/Moscow", nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_reminder_settings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_reminder_settings")),
    )
    op.create_table(
        "reminder_deliveries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("last_outcome", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'claimed', 'sent', 'failed', 'cancelled')",
            name=op.f("ck_reminder_deliveries_reminder_delivery_status"),
        ),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND 3", name=op.f("ck_reminder_deliveries_reminder_attempts")
        ),
        sa.CheckConstraint(
            "(status = 'claimed' AND claim_token IS NOT NULL AND lease_until IS NOT NULL) OR (status <> 'claimed' AND lease_until IS NULL)",
            name=op.f("ck_reminder_deliveries_reminder_claim_lease"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_reminder_deliveries_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminder_deliveries")),
        sa.UniqueConstraint(
            "user_id", "local_date", name=op.f("uq_reminder_deliveries_user_id_local_date")
        ),
    )
    op.create_index(
        "ix_reminder_deliveries_status_not_before", "reminder_deliveries", ["status", "not_before"]
    )


def downgrade() -> None:
    op.drop_index("ix_reminder_deliveries_status_not_before", table_name="reminder_deliveries")
    op.drop_table("reminder_deliveries")
    op.drop_table("reminder_settings")
