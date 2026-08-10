"""create contact_messages table

Revision ID: 0056
Revises: 0055
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0056"
down_revision: Union[str, None] = "0055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This table can already exist on a database where an earlier deploy hit a since-fixed
    # migration crash further up the chain (0049) — app/main.py's lifespan() falls back to
    # Base.metadata.create_all() whenever alembic itself fails, which creates any MISSING
    # table (including this one) straight from the ORM model, bypassing alembic entirely.
    # That leaves alembic_version behind while the table already exists, so a plain
    # create_table() here fails with DuplicateTable and blocks every migration after it
    # (crucially 0057, a real DATA fix that create_all() cannot substitute for). Guard both
    # the table and the index so this migration can't block that recovery path again.
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("contact_messages"):
        op.create_table(
            "contact_messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("email", sa.String(length=200), nullable=False),
            sa.Column("subject", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    have = {i["name"] for i in insp.get_indexes("contact_messages")} if insp.has_table("contact_messages") else set()
    if "ix_contact_messages_email" not in have:
        op.create_index("ix_contact_messages_email", "contact_messages", ["email"])


def downgrade() -> None:
    op.drop_index("ix_contact_messages_email", table_name="contact_messages")
    op.drop_table("contact_messages")
