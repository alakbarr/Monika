@echo off
REM ==============================================================================
REM Isolated CI & Unit Test Runner for Monika Trading Agent (Phase 5.2)
REM Strips live credentials and enforces sandboxed local environment for pytest
REM ==============================================================================

setlocal

set ENVIRONMENT=testing
set PYTEST_CURRENT_TEST=1
set DATABASE_URL=sqlite+aiosqlite:///:memory:
set MT5_ACCOUNT=
set MT5_PASSWORD=
set MT5_SERVER=
set TELEGRAM_BOT_TOKEN=
set TELEGRAM_ADMIN_CHAT_ID=

echo [TestRunner] Running test suite in isolated hermetic environment...
python -m pytest trading-agent/tests %*

endlocal
