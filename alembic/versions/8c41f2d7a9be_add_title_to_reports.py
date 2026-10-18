"""add title to reports

Revision ID: 8c41f2d7a9be
Revises: 3b7d9e1a4c52
Create Date: 2026-10-18 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8c41f2d7a9be'
down_revision: Union[str, Sequence[str], None] = '3b7d9e1a4c52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('reports', sa.Column('title', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('reports', 'title')
