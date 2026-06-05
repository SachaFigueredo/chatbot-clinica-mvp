"""add onboarding fields to tenant_settings

Revision ID: 002
Revises: 001
Create Date: 2026-06-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenant_settings",
        sa.Column("onboarding_state", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "tenant_settings",
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "clinic_configs",
        sa.Column("prices", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clinic_configs", "prices")
    op.drop_column("tenant_settings", "onboarding_completed")
    op.drop_column("tenant_settings", "onboarding_state")
