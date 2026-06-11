"""grandfather existing tenants as subscription, active

Revision ID: 004
Revises: 003
Create Date: 2026-06-10
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Set existing tenants to subscription plan and active status."""
    op.execute(
        "UPDATE tenants SET plan = 'subscription', status = 'active' "
        "WHERE plan != 'subscription'"
    )


def downgrade() -> None:
    """Revert grandfathering: set subscription tenants back to basic."""
    op.execute(
        "UPDATE tenants SET plan = 'basic', status = 'active' "
        "WHERE plan = 'subscription'"
    )
