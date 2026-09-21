#!/usr/bin/env bash
# ==============================================================================
# Isolated CI & Unit Test Runner for Monika Trading Agent (Phase 5.2)
# Strips live credentials and enforces sandboxed local environment for pytest
# ==============================================================================

set -e

export ENVIRONMENT=testing
export PYTEST_CURRENT_TEST=1
export DATABASE_URL="sqlite+aiosqlite:///:memory:"
unset MT5_ACCOUNT
unset MT5_PASSWORD
unset MT5_SERVER
unset TELEGRAM_BOT_TOKEN
unset TELEGRAM_ADMIN_CHAT_ID

echo "[TestRunner] Running test suite in isolated hermetic environment..."
python -m pytest trading-agent/tests "$@"
