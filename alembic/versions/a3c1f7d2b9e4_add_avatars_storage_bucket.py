"""add avatars storage bucket

Revision ID: a3c1f7d2b9e4
Revises: 8637ab414d12
Create Date: 2026-09-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a3c1f7d2b9e4'
down_revision: Union[str, Sequence[str], None] = '8637ab414d12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Users may only write under a folder named after their own auth uid: avatars/<uid>/<file>.
_OWN_FOLDER = "bucket_id = 'avatars' AND (storage.foldername(name))[1] = auth.uid()::text"


def upgrade() -> None:
    """Upgrade schema."""
    # Public bucket: avatar images are served without auth, so no SELECT policy is needed.
    op.execute(
        """
        INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
        VALUES ('avatars', 'avatars', true, 2097152, ARRAY['image/png', 'image/jpeg', 'image/gif'])
        ON CONFLICT (id) DO NOTHING
        """
    )
    for action, clause in (
        ("INSERT", f"WITH CHECK ({_OWN_FOLDER})"),
        ("UPDATE", f"USING ({_OWN_FOLDER})"),
        ("DELETE", f"USING ({_OWN_FOLDER})"),
    ):
        op.execute(
            f'CREATE POLICY "avatars_{action.lower()}_own" ON storage.objects '
            f"FOR {action} TO authenticated {clause}"
        )


def downgrade() -> None:
    """Downgrade schema."""
    for action in ("insert", "update", "delete"):
        op.execute(f'DROP POLICY IF EXISTS "avatars_{action}_own" ON storage.objects')
    op.execute("DELETE FROM storage.buckets WHERE id = 'avatars'")
