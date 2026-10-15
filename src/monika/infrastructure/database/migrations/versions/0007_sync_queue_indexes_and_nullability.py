"""sync_queue_indexes_and_nullability

Revision ID: 0007_sync_queue_schemas
Revises: 0006_consolidate_and_numeric
Create Date: 2026-10-15 14:42:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_sync_queue_schemas"
down_revision: Union[str, Sequence[str], None] = "0006_consolidate_and_numeric"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: sync queue tables column nullability and missing indexes."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    def _has_table(tbl: str) -> bool:
        return tbl in existing_tables

    def _has_column(tbl: str, col: str) -> bool:
        if tbl not in existing_tables:
            return False
        return any(c.get("name") == col for c in insp.get_columns(tbl))

    def _has_index(tbl: str, idx_name: str) -> bool:
        if tbl not in existing_tables or not hasattr(insp, "get_indexes"):
            return False
        return any(i.get("name") == idx_name for i in insp.get_indexes(tbl))

    # 1. cron_jobs nullability
    if _has_table("cron_jobs"):
        with op.batch_alter_table("cron_jobs") as batch_op:
            if _has_column("cron_jobs", "name"):
                batch_op.alter_column("name", existing_type=sa.String(128), nullable=False, server_default="")
            if _has_column("cron_jobs", "is_active"):
                batch_op.alter_column("is_active", existing_type=sa.Integer(), nullable=False, server_default="1")
            if _has_column("cron_jobs", "no_agent"):
                batch_op.alter_column("no_agent", existing_type=sa.Integer(), nullable=False, server_default="0")
            if _has_column("cron_jobs", "pending_slot"):
                batch_op.alter_column("pending_slot", existing_type=sa.Integer(), nullable=False, server_default="0")
            if _has_column("cron_jobs", "timeout_seconds"):
                batch_op.alter_column("timeout_seconds", existing_type=sa.Float(), nullable=False, server_default="0.0")

    # 2. delivery_records nullability and indexes
    if _has_table("delivery_records"):
        with op.batch_alter_table("delivery_records") as batch_op:
            if _has_column("delivery_records", "attempts"):
                batch_op.alter_column("attempts", existing_type=sa.Integer(), nullable=False, server_default="0")
            if _has_column("delivery_records", "max_attempts"):
                batch_op.alter_column("max_attempts", existing_type=sa.Integer(), nullable=False, server_default="3")
            if _has_column("delivery_records", "flood_not_before"):
                batch_op.alter_column(
                    "flood_not_before", existing_type=sa.Float(), nullable=False, server_default="0.0"
                )

        if not _has_index("delivery_records", "ix_delivery_records_flood_not_before"):
            op.create_index(
                "ix_delivery_records_flood_not_before", "delivery_records", ["flood_not_before"], unique=False
            )
        if not _has_index("delivery_records", "ix_delivery_records_status"):
            op.create_index("ix_delivery_records_status", "delivery_records", ["status"], unique=False)

    # 3. outbox_deliveries nullability and index
    if _has_table("outbox_deliveries"):
        with op.batch_alter_table("outbox_deliveries") as batch_op:
            if _has_column("outbox_deliveries", "status"):
                batch_op.alter_column("status", existing_type=sa.String(32), nullable=False, server_default="pending")
            if _has_column("outbox_deliveries", "lease_expires_at"):
                batch_op.alter_column(
                    "lease_expires_at", existing_type=sa.Float(), nullable=False, server_default="0.0"
                )
            if _has_column("outbox_deliveries", "retry_count"):
                batch_op.alter_column("retry_count", existing_type=sa.Integer(), nullable=False, server_default="0")

        if not _has_index("outbox_deliveries", "ix_outbox_deliveries_lease_expires_at"):
            op.create_index(
                "ix_outbox_deliveries_lease_expires_at", "outbox_deliveries", ["lease_expires_at"], unique=False
            )

    # 4. repair_ledger nullability and index
    if _has_table("repair_ledger"):
        with op.batch_alter_table("repair_ledger") as batch_op:
            if _has_column("repair_ledger", "status"):
                batch_op.alter_column("status", existing_type=sa.String(32), nullable=False, server_default="pending")

        if not _has_index("repair_ledger", "ix_repair_ledger_session_id"):
            op.create_index("ix_repair_ledger_session_id", "repair_ledger", ["session_id"], unique=False)

    # 5. scheduled_jobs nullability
    if _has_table("scheduled_jobs"):
        with op.batch_alter_table("scheduled_jobs") as batch_op:
            if _has_column("scheduled_jobs", "is_active"):
                batch_op.alter_column("is_active", existing_type=sa.Integer(), nullable=False, server_default="1")

    # 6. session_tool_records nullability
    if _has_table("session_tool_records"):
        with op.batch_alter_table("session_tool_records") as batch_op:
            if _has_column("session_tool_records", "is_error"):
                batch_op.alter_column("is_error", existing_type=sa.Integer(), nullable=False, server_default="0")
            if _has_column("session_tool_records", "has_side_effects"):
                batch_op.alter_column(
                    "has_side_effects", existing_type=sa.Integer(), nullable=False, server_default="0"
                )


def downgrade() -> None:
    """Downgrade schema: revert nullability constraints and drop added indexes."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    def _has_table(tbl: str) -> bool:
        return tbl in existing_tables

    def _has_column(tbl: str, col: str) -> bool:
        if tbl not in existing_tables:
            return False
        return any(c.get("name") == col for c in insp.get_columns(tbl))

    def _has_index(tbl: str, idx_name: str) -> bool:
        if tbl not in existing_tables or not hasattr(insp, "get_indexes"):
            return False
        return any(i.get("name") == idx_name for i in insp.get_indexes(tbl))

    # 1. Drop added indexes
    if _has_index("repair_ledger", "ix_repair_ledger_session_id"):
        op.drop_index("ix_repair_ledger_session_id", table_name="repair_ledger")
    if _has_index("outbox_deliveries", "ix_outbox_deliveries_lease_expires_at"):
        op.drop_index("ix_outbox_deliveries_lease_expires_at", table_name="outbox_deliveries")
    if _has_index("delivery_records", "ix_delivery_records_status"):
        op.drop_index("ix_delivery_records_status", table_name="delivery_records")
    if _has_index("delivery_records", "ix_delivery_records_flood_not_before"):
        op.drop_index("ix_delivery_records_flood_not_before", table_name="delivery_records")

    # 2. Revert nullability
    if _has_table("session_tool_records"):
        with op.batch_alter_table("session_tool_records") as batch_op:
            if _has_column("session_tool_records", "is_error"):
                batch_op.alter_column("is_error", existing_type=sa.Integer(), nullable=True, server_default="0")
            if _has_column("session_tool_records", "has_side_effects"):
                batch_op.alter_column("has_side_effects", existing_type=sa.Integer(), nullable=True, server_default="0")

    if _has_table("scheduled_jobs"):
        with op.batch_alter_table("scheduled_jobs") as batch_op:
            if _has_column("scheduled_jobs", "is_active"):
                batch_op.alter_column("is_active", existing_type=sa.Integer(), nullable=True, server_default="1")

    if _has_table("repair_ledger"):
        with op.batch_alter_table("repair_ledger") as batch_op:
            if _has_column("repair_ledger", "status"):
                batch_op.alter_column("status", existing_type=sa.String(32), nullable=True, server_default="pending")

    if _has_table("outbox_deliveries"):
        with op.batch_alter_table("outbox_deliveries") as batch_op:
            if _has_column("outbox_deliveries", "status"):
                batch_op.alter_column("status", existing_type=sa.String(32), nullable=True, server_default="pending")
            if _has_column("outbox_deliveries", "lease_expires_at"):
                batch_op.alter_column("lease_expires_at", existing_type=sa.Float(), nullable=True, server_default="0.0")
            if _has_column("outbox_deliveries", "retry_count"):
                batch_op.alter_column("retry_count", existing_type=sa.Integer(), nullable=True, server_default="0")

    if _has_table("delivery_records"):
        with op.batch_alter_table("delivery_records") as batch_op:
            if _has_column("delivery_records", "attempts"):
                batch_op.alter_column("attempts", existing_type=sa.Integer(), nullable=True, server_default="0")
            if _has_column("delivery_records", "max_attempts"):
                batch_op.alter_column("max_attempts", existing_type=sa.Integer(), nullable=True, server_default="3")
            if _has_column("delivery_records", "flood_not_before"):
                batch_op.alter_column("flood_not_before", existing_type=sa.Float(), nullable=True, server_default="0.0")

    if _has_table("cron_jobs"):
        with op.batch_alter_table("cron_jobs") as batch_op:
            if _has_column("cron_jobs", "name"):
                batch_op.alter_column("name", existing_type=sa.String(128), nullable=True, server_default="")
            if _has_column("cron_jobs", "is_active"):
                batch_op.alter_column("is_active", existing_type=sa.Integer(), nullable=True, server_default="1")
            if _has_column("cron_jobs", "no_agent"):
                batch_op.alter_column("no_agent", existing_type=sa.Integer(), nullable=True, server_default="0")
            if _has_column("cron_jobs", "pending_slot"):
                batch_op.alter_column("pending_slot", existing_type=sa.Integer(), nullable=True, server_default="0")
            if _has_column("cron_jobs", "timeout_seconds"):
                batch_op.alter_column("timeout_seconds", existing_type=sa.Float(), nullable=True, server_default="0.0")
