"""sync position paper index, active order index, and foreign keys

Revision ID: 0012_sync_indexes_and_constraints
Revises: 0011_sync_indexes_constraints
Create Date: 2026-10-23 07:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_sync_indexes_and_constraints"
down_revision: Union[str, Sequence[str], None] = "0011_sync_indexes_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Include is_paper in position unique index, add active order index, and add missing FKs."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    # 0. Ensure alembic_version.version_num can store >32-char revision IDs on PostgreSQL
    if "alembic_version" in existing_tables and bind.dialect.name == "postgresql":
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=sa.String(32),
            type_=sa.String(64),
            existing_nullable=False,
        )

    # 1. Update uq_position_symbol_open on positions
    if "positions" in existing_tables:
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("positions")}
        if "uq_position_symbol_open" in existing_indexes:
            op.drop_index("uq_position_symbol_open", table_name="positions")
        op.create_index(
            "uq_position_symbol_open",
            "positions",
            ["symbol", "is_paper"],
            unique=True,
            postgresql_where=sa.text("status = 'open' AND pair_group_id IS NULL"),
            sqlite_where=sa.text("status = 'open' AND pair_group_id IS NULL"),
        )

    # 2. Add uq_orders_symbol_active on orders
    if "orders" in existing_tables:
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("orders")}
        if "uq_orders_symbol_active" not in existing_indexes:
            op.create_index(
                "uq_orders_symbol_active",
                "orders",
                ["symbol"],
                unique=True,
                postgresql_where=sa.text("status IN ('pending_submit', 'intent_committed', 'submitted', 'accepted')"),
                sqlite_where=sa.text("status IN ('pending_submit', 'intent_committed', 'submitted', 'accepted')"),
            )

    # 3. Add foreign key on agent_session_messages.session_id -> agent_sessions.id
    if "agent_session_messages" in existing_tables and "agent_sessions" in existing_tables:
        get_fks = getattr(insp, "get_foreign_keys", lambda t: [])
        fk_names = {fk.get("name") for fk in get_fks("agent_session_messages")}
        if "fk_asm_session_id" not in fk_names:
            with op.batch_alter_table("agent_session_messages") as batch_op:
                batch_op.create_foreign_key(
                    "fk_asm_session_id",
                    "agent_sessions",
                    ["session_id"],
                    ["id"],
                    ondelete="CASCADE",
                )

    # 4. Add foreign key on decision_reflections.position_id -> positions.id
    if "decision_reflections" in existing_tables and "positions" in existing_tables:
        get_fks = getattr(insp, "get_foreign_keys", lambda t: [])
        fk_names = {fk.get("name") for fk in get_fks("decision_reflections")}
        if "fk_dr_position_id" not in fk_names:
            with op.batch_alter_table("decision_reflections") as batch_op:
                batch_op.create_foreign_key(
                    "fk_dr_position_id",
                    "positions",
                    ["position_id"],
                    ["id"],
                    ondelete="SET NULL",
                )


def downgrade() -> None:
    """Downgrade schema: Revert uq_position_symbol_open, drop active order index, and drop added FKs."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    # 1. Revert uq_position_symbol_open on positions
    if "positions" in existing_tables:
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("positions")}
        if "uq_position_symbol_open" in existing_indexes:
            op.drop_index("uq_position_symbol_open", table_name="positions")
        op.create_index(
            "uq_position_symbol_open",
            "positions",
            ["symbol"],
            unique=True,
            postgresql_where=sa.text("status = 'open' AND pair_group_id IS NULL"),
            sqlite_where=sa.text("status = 'open' AND pair_group_id IS NULL"),
        )

    # 2. Drop uq_orders_symbol_active on orders
    if "orders" in existing_tables:
        existing_indexes = {idx.get("name") for idx in insp.get_indexes("orders")}
        if "uq_orders_symbol_active" in existing_indexes:
            op.drop_index("uq_orders_symbol_active", table_name="orders")

    # 3. Drop foreign key on decision_reflections
    if "decision_reflections" in existing_tables:
        with op.batch_alter_table("decision_reflections") as batch_op:
            batch_op.drop_constraint("fk_dr_position_id", type_="foreignkey")

    # 4. Drop foreign key on agent_session_messages
    if "agent_session_messages" in existing_tables:
        with op.batch_alter_table("agent_session_messages") as batch_op:
            batch_op.drop_constraint("fk_asm_session_id", type_="foreignkey")
