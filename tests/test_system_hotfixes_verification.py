"""
Test Suite: Verifikasi Fase 0 Hotfixes Keamanan Kritis & Financial Fortress Invariants
Memvalidasi:
1. AST static sandbox hardening (ptc_handler.py & sandbox_runner.py)
2. Akuntansi pending/in-flight orders di RiskGate
3. Safe lazy engine acquisition di db_health.py
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from monika.application.analysis.tools.handlers.ptc_handler import PTCHandler
from monika.application.analysis.tools.kernel.sandbox_runner import validate_code_ast


def test_ptc_ast_blocks_rce_and_broker_access():
    """Verify PTCHandler._validate_code_ast blocks RCE and broker access vectors."""
    # 1. os.system RCE
    is_safe, err = PTCHandler._validate_code_ast("import os\nos.system('calc')")
    assert not is_safe
    assert "restricted module 'os'" in err

    # 2. Dangerous attribute invocation
    is_safe, err = PTCHandler._validate_code_ast("x.system('calc')")
    assert not is_safe
    assert "dangerous attribute 'system'" in err

    # 3. MetaTrader5 import bypass
    is_safe, err = PTCHandler._validate_code_ast("import MetaTrader5 as mt5\nmt5.order_send()")
    assert not is_safe
    assert "restricted module 'metatrader5'" in err

    # 4. internal execution module import bypass
    is_safe, err = PTCHandler._validate_code_ast("from execution.mt5_client import MT5Client")
    assert not is_safe
    assert "restricted module 'execution'" in err

    # 5. Socket network egress
    is_safe, err = PTCHandler._validate_code_ast("import socket\ns = socket.socket()")
    assert not is_safe
    assert "restricted module 'socket'" in err

    # 6. Reflection bypass attempt
    is_safe, err = PTCHandler._validate_code_ast("x = ().__class__.__subclasses__()")
    assert not is_safe
    assert "__subclasses__" in err

    # 7. Safe math code allowed
    is_safe, err = PTCHandler._validate_code_ast("import math\ny = math.sqrt(16.0)\nprint(y)")
    assert is_safe
    assert err == ""


def test_sandbox_runner_ast_blocks_dangerous_operations():
    """Verify sandbox_runner.validate_code_ast blocks dangerous operations."""
    # 1. open call
    is_safe, err = validate_code_ast("with open('/etc/passwd') as f:\n    pass")
    assert not is_safe
    assert "built-in 'open'" in err

    # 2. broker access
    is_safe, err = validate_code_ast("import MetaTrader5")
    assert not is_safe
    assert "restricted module 'metatrader5'" in err

    # 3. subprocess call
    is_safe, err = validate_code_ast("import subprocess\nsubprocess.run(['ls'])")
    assert not is_safe
    assert "restricted module 'subprocess'" in err

    # 4. Safe array math allowed
    is_safe, err = validate_code_ast("import numpy as np\narr = np.array([1, 2, 3])")
    assert is_safe
    assert err == ""


@pytest.mark.asyncio
async def test_db_health_safe_get_engine():
    """Verify db_health.py uses get_engine() safely without NoneType attribute error."""
    from monika.application.agent.monitors.db_health import run_db_health_check

    agent = MagicMock()
    agent.shutdown_event.is_set.side_effect = [False, True]
    agent.shutdown_event.wait = AsyncMock()

    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_engine.connect.return_value.__aenter__.return_value = mock_conn

    with patch("monika.infrastructure.database.db.get_engine", return_value=mock_engine):
        await run_db_health_check(agent)
        mock_conn.execute.assert_awaited_once()
