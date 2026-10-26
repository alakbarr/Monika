"""add is_paid and cost_source to token_usage_log

Revision ID: 0013_token_usage_cost_source_and_is_paid
Revises: 0012_sync_indexes_and_constraints
Create Date: 2026-10-27 01:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_token_usage_cost_source_and_is_paid"
down_revision: Union[str, Sequence[str], None] = "0012_sync_indexes_and_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Add is_paid and cost_source columns and indexes to token_usage_log."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "token_usage_log" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("token_usage_log")}
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("token_usage_log")}

        is_postgres = bind.dialect.name == "postgresql"
        bool_default = sa.text("false" if is_postgres else "0")

        with op.batch_alter_table("token_usage_log") as batch_op:
            if "is_paid" not in existing_cols:
                batch_op.add_column(sa.Column("is_paid", sa.Boolean(), server_default=bool_default, nullable=False))
            if "cost_source" not in existing_cols:
                batch_op.add_column(sa.Column("cost_source", sa.String(length=32), nullable=True))

        if "ix_token_usage_log_is_paid" not in existing_indexes:
            op.create_index("ix_token_usage_log_is_paid", "token_usage_log", ["is_paid"])
        if "ix_token_usage_log_cost_source" not in existing_indexes:
            op.create_index("ix_token_usage_log_cost_source", "token_usage_log", ["cost_source"])


def downgrade() -> None:
    """Downgrade schema: Drop indexes and columns is_paid and cost_source from token_usage_log."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    if "token_usage_log" in existing_tables:
        existing_cols = {c["name"] for c in insp.get_columns("token_usage_log")}
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("token_usage_log")}

        if "ix_token_usage_log_cost_source" in existing_indexes:
            op.drop_index("ix_token_usage_log_cost_source", table_name="token_usage_log")
        if "ix_token_usage_log_is_paid" in existing_indexes:
            op.drop_index("ix_token_usage_log_is_paid", table_name="token_usage_log")

        with op.batch_alter_table("token_usage_log") as batch_op:
            if "cost_source" in existing_cols:
                batch_op.drop_column("cost_source")
            if "is_paid" in existing_cols:
                batch_op.drop_column("is_paid")
