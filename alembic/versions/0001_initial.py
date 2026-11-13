"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-03
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Crea todas las tablas definidas en models.py."""
    from models import Base
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    """Elimina todas las tablas (⚠️ destructivo)."""
    from models import Base
    Base.metadata.drop_all(bind=op.get_bind())
