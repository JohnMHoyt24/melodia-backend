"""add user_artists (personal libraries)

Revision ID: d7e4a9b3c2f1
Revises: c5d8e2f1a7b3
Create Date: 2026-09-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7e4a9b3c2f1'
down_revision: Union[str, Sequence[str], None] = 'c5d8e2f1a7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'user_artists',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('artist_id', sa.Uuid(), nullable=False),
        sa.Column('added_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['artist_id'], ['artists.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'artist_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('user_artists')
