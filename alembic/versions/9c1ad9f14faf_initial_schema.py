"""initial_schema

Revision ID: 9c1ad9f14faf
Revises:
Create Date: 2026-06-23 05:17:13.327288

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "9c1ad9f14faf"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
