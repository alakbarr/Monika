# ==============================================================================
# File: tests/telegram_bot/test_chat_database_access.py
# ==============================================================================

"""
Unit tests for ChatAgent database inspection and mutation features.
Verifies admin-only gating, schema introspection, bounded query execution,
guardrail enforcement for immutable tables, and two-phase mutation lifecycle.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.tools.handlers.db_tools import (
    handle_inspect_database_schema,
    handle_read_database_records,
    get_table_model_map,
)
from analysis.tools.tool_guardrails import (
    ToolGuardrailController,
    DATABASE_IMMUTABLE_TABLES,
)
from telegram_bot.chat_agent import ChatAgent, PendingAction


class DummyExecutor:
    def __init__(self, is_admin: bool = True, session=None):
        self.is_admin = is_admin
        self.session = session


@pytest.mark.asyncio
async def test_inspect_database_schema_admin_gating():
    """Non-admin must be denied schema inspection, while Admin succeeds."""
    non_admin_exec = DummyExecutor(is_admin=False)
    res_denied = await handle_inspect_database_schema({}, executor=non_admin_exec)
    assert res_denied["status"] == "error"
    assert "Akses Ditolak" in res_denied["error"]

    admin_exec = DummyExecutor(is_admin=True)
    res_allowed = await handle_inspect_database_schema({}, executor=admin_exec)
    assert res_allowed["status"] == "success"
    assert res_allowed["total_tables"] >= 40
    table_names = [t["table"] for t in res_allowed["tables"]]
    assert "system_config" in table_names
    assert "positions" in table_names


@pytest.mark.asyncio
async def test_inspect_database_schema_single_table():
    """Admin can inspect specific table columns and details."""
    admin_exec = DummyExecutor(is_admin=True)
    res = await handle_inspect_database_schema({"table_name": "system_config"}, executor=admin_exec)
    assert res["status"] == "success"
    assert res["table"] == "system_config"
    col_names = [c["name"] for c in res["columns"]]
    assert "key" in col_names
    assert "value" in col_names


@pytest.mark.asyncio
async def test_read_database_records_admin_gating_and_validation():
    """Non-admin must be denied reading records, invalid tables rejected."""
    mock_session = AsyncMock()
    non_admin_exec = DummyExecutor(is_admin=False, session=mock_session)

    res_denied = await handle_read_database_records(
        {"table_name": "system_config"}, session=mock_session, executor=non_admin_exec
    )
    assert res_denied["status"] == "error"
    assert "Akses Ditolak" in res_denied["error"]

    admin_exec = DummyExecutor(is_admin=True, session=mock_session)
    res_invalid_tbl = await handle_read_database_records(
        {"table_name": "non_existent_table_123"}, session=mock_session, executor=admin_exec
    )
    assert res_invalid_tbl["status"] == "error"
    assert "tidak valid" in res_invalid_tbl["error"]


def test_guardrails_protect_immutable_tables():
    """Guardrails must strictly block db_mutation on immutable audit tables."""
    controller = ToolGuardrailController()
    context = {"is_admin": True}

    for tbl in DATABASE_IMMUTABLE_TABLES:
        args = {
            "action_type": "db_mutation",
            "params": {
                "table_name": tbl,
                "operation": "delete",
                "target_id": 1,
            },
        }
        verdict = controller.validate_tool_call("propose_action", args, context=context)
        assert not verdict.allowed
        assert verdict.guard_name == "ImmutableTableGuard"
        assert tbl in verdict.reason


def test_guardrails_require_target_id_for_update_and_delete():
    """Guardrails must require target_id for UPDATE and DELETE operations."""
    controller = ToolGuardrailController()
    context = {"is_admin": True}

    # Update without target_id
    verdict_update = controller.validate_tool_call(
        "propose_action",
        {
            "action_type": "db_mutation",
            "params": {
                "table_name": "system_config",
                "operation": "update",
                "data": {"value": "new_val"},
            },
        },
        context=context,
    )
    assert not verdict_update.allowed
    assert verdict_update.guard_name == "TargetIdRequiredGuard"

    # Delete without target_id
    verdict_delete = controller.validate_tool_call(
        "propose_action",
        {
            "action_type": "db_mutation",
            "params": {
                "table_name": "system_config",
                "operation": "delete",
            },
        },
        context=context,
    )
    assert not verdict_delete.allowed
    assert verdict_delete.guard_name == "TargetIdRequiredGuard"


def test_guardrails_block_non_admin_db_mutation():
    """Guardrails must block non-admin users from proposing db_mutation."""
    controller = ToolGuardrailController()
    context = {"is_admin": False}

    verdict = controller.validate_tool_call(
        "propose_action",
        {
            "action_type": "db_mutation",
            "params": {
                "table_name": "system_config",
                "operation": "update",
                "target_id": "test_key",
                "data": {"value": "123"},
            },
        },
        context=context,
    )
    assert not verdict.allowed
    assert verdict.guard_name == "AdminOnlyGuard"


@pytest.mark.asyncio
async def test_chat_agent_create_pending_action_db_mutation():
    """ChatAgent should create a valid PendingAction with formatted description for db_mutation."""
    agent = ChatAgent(settings={}, user_id=12345, is_admin=True)
    proposed = {
        "action_type": "db_mutation",
        "params": {
            "table_name": "system_config",
            "operation": "update",
            "target_id": "auto_execute",
            "data": {"value": "true"},
            "reason": "Operator requested auto execute",
        },
        "reason": "Operator requested auto execute",
    }
    pending = agent._create_pending_action(proposed)
    assert pending is not None
    assert pending.action_type == "db_mutation"
    assert "Modifikasi Database" in pending.description
    assert "UPDATE" in pending.description
    assert "auto_execute" in pending.description


@pytest.mark.asyncio
async def test_chat_agent_execute_db_mutation_non_admin():
    """_execute_db_mutation must reject execution if agent is not admin."""
    agent = ChatAgent(settings={}, user_id=99999, is_admin=False)
    params = {
        "table_name": "system_config",
        "operation": "update",
        "target_id": "foo",
        "data": {"value": "bar"},
    }
    res = await agent._execute_db_mutation(params)
    assert "Hanya Admin" in res
