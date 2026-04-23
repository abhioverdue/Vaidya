"""add_users

Revision ID: 0002_add_users
Revises: 0001_initial_schema
Create Date: 2026-04-17 00:00:00.000000

Adds the `users` table for account-based authentication.
Re-run safety: guarded by _table_exists().
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect, text

revision = "0002_add_users"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def _table_exists(bind, name: str) -> bool:
    return inspect(bind).has_table(name)


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "users"):
        return

    is_sqlite = bind.dialect.name == "sqlite"

    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.String(36) if is_sqlite else postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column("name",          sa.String(200), nullable=False),
        sa.Column("phone",         sa.String(20),  nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("age_group",     sa.String(20),  nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_table("users")
