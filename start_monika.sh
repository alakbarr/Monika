#!/usr/bin/env bash
# ==============================================================================
# Monika — Autonomous MT5 Trading Agent Interactive Launcher (Linux / VPS)
# Provides one-click environment bootstrap, setup wizard, and crash recovery.
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

export PYTHONPATH="${SCRIPT_DIR}/src:${PYTHONPATH}"
export PYTHONUNBUFFERED=1

VENV_DIR="${SCRIPT_DIR}/venv"
if [ ! -f "${VENV_DIR}/bin/python" ] && [ -f "${SCRIPT_DIR}/.venv/bin/python" ]; then
    VENV_DIR="${SCRIPT_DIR}/.venv"
fi
PYTHON_EXE="${VENV_DIR}/bin/python"

echo "============================================================"
echo "  MONIKA - Autonomous MT5 Quantitative Trading Agent"
echo "============================================================"
echo ""

# ── 0. Anti-Collision Pre-Flight Check (Docker vs Host) ───────
if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -q "monika-agent"; then
    echo "[!] Monika is currently running inside Docker container 'monika-agent'."
    echo "    Running standalone on host simultaneously would cause port 8000 collisions."
    echo ""
    echo "    Management options:"
    echo "      * View logs:    docker compose -f deploy/docker-compose.vps.yml logs -f agent"
    echo "      * Restart:      docker compose -f deploy/docker-compose.vps.yml restart agent"
    echo "      * Stop Docker:  docker compose -f deploy/docker-compose.vps.yml down"
    echo ""
    read -r -p "Stop Docker services now and run standalone on host? (y/N): " STOP_DOCKER || true
    if [[ "$STOP_DOCKER" =~ ^[Yy]$ ]]; then
        echo "[*] Stopping Docker services..."
        docker compose -f deploy/docker-compose.vps.yml down
    else
        echo "[*] Keeping Docker container running. Exiting host launcher."
        exit 0
    fi
fi

# ── 1. Verify System Python ───────────────────────────────────
SYS_PYTHON=""
if command -v python3 &>/dev/null; then
    SYS_PYTHON="python3"
elif command -v python &>/dev/null; then
    SYS_PYTHON="python"
fi

if [ -z "${SYS_PYTHON}" ]; then
    echo "[ERROR] Python 3 is not found in system PATH."
    echo "Please install Python 3.12+ or 3.14+ (e.g. sudo apt install python3 python3-venv python3-pip)"
    exit 1
fi

PY_VER=$(${SYS_PYTHON} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
echo "[OK] System Python detected: ${SYS_PYTHON} (v${PY_VER})"

# ── 2. Virtual Environment & Dependencies ─────────────────────
if [ ! -f "${PYTHON_EXE}" ]; then
    echo ""
    echo "[*] [1/3] Creating virtual environment at venv..."
    ${SYS_PYTHON} -m venv "${VENV_DIR}" || {
        echo "[ERROR] Failed to create virtual environment."
        echo "Make sure python3-venv is installed: sudo apt install python3-venv"
        exit 1
    }
    echo "[OK] Virtual environment created."

    echo "[*] [2/3] Installing dependencies - this takes 1-2 minutes on first run..."
    "${VENV_DIR}/bin/pip" install --upgrade pip >/dev/null 2>&1 || true
    "${VENV_DIR}/bin/pip" install -r "${SCRIPT_DIR}/requirements.txt" || {
        echo "[WARN] Some dependencies encountered warnings. Continuing to pre-flight checks..."
    }
    "${VENV_DIR}/bin/pip" install -e . --no-deps >/dev/null 2>&1 || true
    echo "[OK] Dependencies initialized."
else
    echo "[OK] Python virtual environment ready."
fi

# Ensure data and log directories exist
mkdir -p "${SCRIPT_DIR}/logs" "${SCRIPT_DIR}/data"

# ── 3. Check Configuration (.env) ─────────────────────────────
run_setup=false
if [ "$1" = "setup" ] || [ "$1" = "--setup" ]; then
    run_setup=true
    shift
fi

if [ ! -f "${SCRIPT_DIR}/.env" ] || [ "$run_setup" = true ]; then
    echo ""
    echo "[*] [3/3] Monika is not yet configured or setup was requested."
    echo "[*] Launching Guided Interactive Setup Wizard..."
    echo ""
    "${PYTHON_EXE}" -m monika.interfaces.cli.main setup || {
        echo "[ERROR] Setup wizard did not finish. Run ./start_monika.sh again when ready."
        exit 1
    }
    echo ""
    echo "[*] Running automated system health verification (doctor --fix)..."
    "${PYTHON_EXE}" -m monika.interfaces.cli.main doctor --fix || true
    echo "[OK] Setup and system verification completed successfully!"
    echo ""
fi

# ── 4. Detect or Select Installation Tier (Trial vs Full) ────
CURRENT_TIER="trial"
if [ -f "${SCRIPT_DIR}/.monika_tier" ]; then
    CURRENT_TIER=$(cat "${SCRIPT_DIR}/.monika_tier" | tr -d '[:space:]')
fi

NON_INTERACTIVE=false
if [ "$1" = "run" ] || [ "$1" = "--daemon" ] || [ "$1" = "--non-interactive" ]; then
    NON_INTERACTIVE=true
    shift
fi

if [ "$1" = "full" ]; then
    CURRENT_TIER="full"
    shift
elif [ "$1" = "trial" ]; then
    CURRENT_TIER="trial"
    shift
fi

if [ "$NON_INTERACTIVE" = false ]; then
    echo "============================================================"
    echo "  MONIKA PACKAGE SELECTION / RUNNING TIER:"
    echo "============================================================"
    if [ "$CURRENT_TIER" = "full" ]; then
        echo "  1. [1] Switch to Trial Package"
        echo "         - Paper Trading + SQLite + CLI / Telegram"
        echo "  2. [2] Continue with Full Package [Active Default]"
        echo "         - PostgreSQL + React Web Dashboard + 9Router AI Gateway"
        DEFAULT_CHOICE="2"
    else
        echo "  1. [1] Continue with Trial Package [Active Default]"
        echo "         - Paper Trading + SQLite + CLI / Telegram"
        echo "  2. [2] Switch to Full Package"
        echo "         - PostgreSQL + React Web Dashboard + 9Router AI Gateway"
        DEFAULT_CHOICE="1"
    fi
    echo "  3. [S] Re-run Guided Setup Wizard"
    echo "  4. [Q] Quit"
    echo "============================================================"

    read -r -p "Select an option [1/2/S/Q, default: ${DEFAULT_CHOICE}]: " TIER_CHOICE || true
    TIER_CHOICE="${TIER_CHOICE:-$DEFAULT_CHOICE}"
    TIER_KEY=$(echo "${TIER_CHOICE:0:1}" | tr '[:upper:]' '[:lower:]')

    case "$TIER_KEY" in
        q)
            echo "[*] Exiting Monika launcher."
            exit 0
            ;;
        s)
            "${PYTHON_EXE}" -m monika.interfaces.cli.main setup
            ;;
        2|f)
            CURRENT_TIER="full"
            ;;
        *)
            CURRENT_TIER="trial"
            ;;
    esac
fi

echo "$CURRENT_TIER" > "${SCRIPT_DIR}/.monika_tier"
echo ""

export MONIKA_TIER="${CURRENT_TIER}"
if [ "$CURRENT_TIER" = "trial" ]; then
    echo "[*] Active Package Tier: Trial Package"
    echo "[*] Engine: Zero-Config SQLite + Paper Trading Simulation."
    echo "[*] Control: Interactive CLI + Telegram Alerts."
    echo "[*] Note: Upgrade anytime to Full Package via: python -m monika.interfaces.cli.main upgrade"
else
    echo "[*] Active Package Tier: Full Package"
    echo "[*] Engine: Enterprise PostgreSQL + 9Router AI Gateway + Web Dashboard."
    echo "[*] Web Dashboard accessible at: http://localhost:8000"
fi
echo ""

# ── 5. Run Loop with Crash Recovery ───────────────────────────
while true; do
    set +e
    "${PYTHON_EXE}" -m monika.interfaces.cli.main run "$@"
    EXIT_CODE=$?
    set -e

    if [ -f "${SCRIPT_DIR}/data/clean_shutdown.flag" ]; then
        rm -f "${SCRIPT_DIR}/data/clean_shutdown.flag"
        echo ""
        echo "[*] Monika agent has shut down gracefully."
        exit 0
    fi

    if [ $EXIT_CODE -eq 0 ]; then
        echo ""
        echo "[*] Monika agent execution ended successfully."
        exit 0
    fi

    echo ""
    echo "============================================================"
    echo "[!] Monika agent exited with code ${EXIT_CODE}."
    echo "============================================================"
    echo "  [R] Retry running Monika"
    echo "  [D] Run Doctor diagnostics and auto-repair (doctor --fix)"
    echo "  [S] Run Setup Wizard to reconfigure settings"
    echo "  [T] Switch Package Tier (Trial <--> Full)"
    echo "  [Q] Quit"
    echo "============================================================"
    read -r -p "Select an action [R/D/S/T/Q, default: R]: " ERR_CHOICE || true
    ERR_CHOICE=$(echo "${ERR_CHOICE:-r}" | tr '[:upper:]' '[:lower:]')

    case "$ERR_CHOICE" in
        d)
            echo ""
            echo "[*] Running Monika Doctor diagnostics and auto-repair..."
            "${PYTHON_EXE}" -m monika.interfaces.cli.main doctor --fix || true
            read -r -p "Press Enter to retry running Monika..."
            ;;
        s)
            "${PYTHON_EXE}" -m monika.interfaces.cli.main setup
            ;;
        t)
            if [ "$CURRENT_TIER" = "trial" ]; then
                CURRENT_TIER="full"
                export MONIKA_TIER="full"
                echo "full" > "${SCRIPT_DIR}/.monika_tier"
                echo "[*] Switched tier to: Full Package."
            else
                CURRENT_TIER="trial"
                export MONIKA_TIER="trial"
                export DATABASE_URL="sqlite+aiosqlite:///data/monika.db"
                export PAPER_TRADING_MODE="true"
                echo "trial" > "${SCRIPT_DIR}/.monika_tier"
                echo "[*] Switched tier to: Trial Package."
            fi
            ;;
        q)
            echo "[*] Exiting Monika launcher."
            exit $EXIT_CODE
            ;;
        *)
            echo "[*] Retrying Monika launch in 3 seconds..."
            sleep 3
            ;;
    esac
done
