#!/usr/bin/env bash
# ==============================================================================
# Isolated CI & Unit Test Runner for Monika Trading Agent (POSIX / Linux / VPS)
# Strips live credentials and enforces sandboxed local environment for pytest
# ==============================================================================
set -euo pipefail

export ENVIRONMENT=testing
export PYTEST_CURRENT_TEST=1
export DATABASE_URL="sqlite+aiosqlite:///:memory:"
export MT5_ACCOUNT=""
export MT5_PASSWORD=""
export MT5_SERVER=""
export TELEGRAM_BOT_TOKEN=""
export TELEGRAM_ADMIN_CHAT_ID=""
export PYTHONPATH="src:${PYTHONPATH:-}"

echo "[TestRunner] Running test suite in isolated hermetic environment..."
python -m pytest tests "$@"
