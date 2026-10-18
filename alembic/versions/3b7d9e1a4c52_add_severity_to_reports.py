"""add severity to reports

Revision ID: 3b7d9e1a4c52
Revises: fca7e5eb1d83
Create Date: 2026-10-18 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3b7d9e1a4c52'
down_revision: Union[str, Sequence[str], None] = 'fca7e5eb1d83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('reports', sa.Column('severity', sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('reports', 'severity')
