"""add billing/subscription fields to tenants

Revision ID: 003
Revises: 002
Create Date: 2026-06-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("mercadopago_customer_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("mercadopago_subscription_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "suspended_at")
    op.drop_column("tenants", "mercadopago_subscription_id")
    op.drop_column("tenants", "mercadopago_customer_id")
    op.drop_column("tenants", "trial_ends_at")
