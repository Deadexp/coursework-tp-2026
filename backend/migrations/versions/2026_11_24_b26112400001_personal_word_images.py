"""Keep uploaded illustrations in the personal dictionary."""

import sqlalchemy as sa
from alembic import op

revision = "b26112400001"
down_revision = "a26111200003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_words", sa.Column("image_data", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_words", "image_data")
