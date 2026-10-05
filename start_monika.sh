#!/usr/bin/env bash
# ==============================================================================
# Monika — Autonomous MT5 Trading Agent (Linux, VPS & macOS Single Launcher)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="${SCRIPT_DIR}/trading-agent"
VENV_DIR="${AGENT_DIR}/venv"
PYTHON_BIN="${VENV_DIR}/bin/python"

echo "============================================================"
echo "  MONIKA - Autonomous MT5 Quantitative Trading Agent"
echo "============================================================"
echo ""

# ── 1. Verify Python 3.11+ ────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 not found. Please install Python 3.11+:"
    echo "  Ubuntu/Debian: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    echo "  Fedora:        sudo dnf install -y python3 python3-pip"
    echo "  macOS:         brew install python@3.11"
    exit 1
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]); then
    echo "[ERROR] Python 3.11+ is required (found Python ${PY_VER})."
    echo "Please update your Python interpreter."
    exit 1
fi

echo "[OK] Python ${PY_VER} detected."

# ── 2. Setup Virtual Environment ──────────────────────────────
if [ ! -f "${PYTHON_BIN}" ]; then
    echo "[*] [1/3] Preparing virtual environment at trading-agent/venv..."
    python3 -m venv "${VENV_DIR}"
    echo "[OK] Virtual environment created."

    echo "[*] [2/3] Installing core dependencies (please wait ~1-2 minutes)..."
    "${VENV_DIR}/bin/pip" install --upgrade pip >/dev/null 2>&1
    "${VENV_DIR}/bin/pip" install -r "${AGENT_DIR}/requirements.txt"
    echo "[OK] Core dependencies installed successfully."
else
    echo "[OK] Python virtual environment detected."
fi

# ── 3. Check Setup Configuration (.env) ──────────────────────
if [ "$1" = "setup" ] || [ "$1" = "--setup" ]; then
    echo ""
    echo "[*] Launching Interactive Setup Wizard..."
    cd "${AGENT_DIR}"
    export PYTHONPATH="${AGENT_DIR}"
    "${PYTHON_BIN}" -m cli.main setup
    "${PYTHON_BIN}" -m cli.main doctor --fix
fi

ENV_FOUND=0
[ -f "${SCRIPT_DIR}/.env" ] && ENV_FOUND=1
[ -f "${AGENT_DIR}/.env" ] && ENV_FOUND=1

if [ $ENV_FOUND -eq 0 ]; then
    echo ""
    echo "[*] [3/3] Monika is not yet configured."
    echo "[*] Launching Interactive Setup Wizard..."
    echo ""

    cd "${AGENT_DIR}"
    export PYTHONPATH="${AGENT_DIR}"
    "${PYTHON_BIN}" -m cli.main setup
    if [ $? -ne 0 ]; then
        echo ""
        echo "[ERROR] Setup wizard did not finish. Run ./start_monika.sh again when ready."
        exit 1
    fi

    echo ""
    echo "[*] Running automated system health verification (Doctor --fix)..."
    "${PYTHON_BIN}" -m cli.main doctor --fix
    echo ""
    echo "[OK] Configuration and system verification completed successfully!"
    echo ""
fi

# ── 4. Detect or Select Installation Tier (Trial vs Full) ────
CURRENT_TIER=""
if [ -f "${SCRIPT_DIR}/.monika_tier" ]; then
    CURRENT_TIER=$(cat "${SCRIPT_DIR}/.monika_tier" | tr -d '[:space:]')
elif [ -f "${AGENT_DIR}/.monika_tier" ]; then
    CURRENT_TIER=$(cat "${AGENT_DIR}/.monika_tier" | tr -d '[:space:]')
fi

if [ "$1" = "full" ]; then
    CURRENT_TIER="full"
elif [ "$1" = "trial" ]; then
    CURRENT_TIER="trial"
fi

if [ -z "${CURRENT_TIER}" ]; then
    CURRENT_TIER="trial"
fi

echo ""
echo "============================================================"
echo "  MONIKA PACKAGE SELECTION / RUNNING TIER:"
echo "============================================================"
if [ "${CURRENT_TIER}" = "trial" ]; then
    echo "  1. [1] Continue with Trial Package [Active Default]"
    echo "         (Paper Trading + SQLite + CLI / Telegram)"
    echo "  2. [2] Switch to Full Package"
    echo "         (PostgreSQL + React Web Dashboard + 9Router AI Gateway)"
    DEFAULT_CHOICE="1"
else
    echo "  1. [1] Switch to Trial Package"
    echo "         (Paper Trading + SQLite + CLI / Telegram)"
    echo "  2. [2] Continue with Full Package [Active Default]"
    echo "         (PostgreSQL + React Web Dashboard + 9Router AI Gateway)"
    DEFAULT_CHOICE="2"
fi
echo "  3. [S] Re-run Guided Setup Wizard"
echo "  4. [Q] Quit"
echo "============================================================"
read -r -p "Select an option [1/2/S/Q, default: ${DEFAULT_CHOICE}]: " TIER_CHOICE
TIER_CHOICE="${TIER_CHOICE:-${DEFAULT_CHOICE}}"

case "${TIER_CHOICE}" in
    [qQ])
        echo "[*] Exiting Monika launcher."
        exit 0
        ;;
    [sS]|[sS]etup)
        cd "${AGENT_DIR}"
        export PYTHONPATH="${AGENT_DIR}"
        "${PYTHON_BIN}" -m cli.main setup
        "${PYTHON_BIN}" -m cli.main doctor --fix
        exec "$0"
        ;;
    2|[fF]ull|[fF])
        CURRENT_TIER="full"
        ;;
    *)
        CURRENT_TIER="trial"
        ;;
esac

echo "${CURRENT_TIER}" > "${SCRIPT_DIR}/.monika_tier"
echo "${CURRENT_TIER}" > "${AGENT_DIR}/.monika_tier"

echo ""
if [ "${CURRENT_TIER}" = "trial" ]; then
    export MONIKA_TIER="trial"
    export DATABASE_URL="sqlite+aiosqlite:///data/monika.db"
    export PAPER_TRADING_MODE="true"
    echo "[*] Active Package Tier: Trial Package"
    echo "[*] Engine: Zero-Config SQLite + Paper Trading Simulation."
    echo "[*] Control: Interactive CLI + Telegram Alerts."
    echo "[*] Note: Upgrade anytime to Full Package via: python -m cli.main upgrade"
else
    export MONIKA_TIER="full"
    unset DATABASE_URL
    unset PAPER_TRADING_MODE
    echo "[*] Active Package Tier: Full Package"
    echo "[*] Engine: Enterprise PostgreSQL + 9Router AI Gateway + Web Dashboard."
    if command -v xdg-open &>/dev/null && [ -n "${DISPLAY}" ]; then
        (sleep 3 && xdg-open "http://localhost:8000") &
    fi
fi
echo ""

# ── 5. Run Monika Trading Agent ──────────────────────────────
cd "${AGENT_DIR}"
export PYTHONPATH="${AGENT_DIR}"

while true; do
    "${PYTHON_BIN}" -m cli.main run "$@"
    EXIT_CODE=$?

    if [ -f "${AGENT_DIR}/data/clean_shutdown.flag" ]; then
        rm -f "${AGENT_DIR}/data/clean_shutdown.flag"
        echo "[*] Monika agent stopped gracefully by operator. Exiting."
        break
    fi

    if [ ${EXIT_CODE} -eq 0 ]; then
        echo "[*] Monika agent execution completed successfully."
        break
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
    read -r -p "Select an action [R=Retry / D=Doctor / S=Setup / T=Switch Tier / Q=Quit, default: R]: " ERR_CHOICE
    case "${ERR_CHOICE}" in
        [dD])
            echo "[*] Running Monika Doctor diagnostics and auto-repair..."
            "${PYTHON_BIN}" -m cli.main doctor --fix
            read -r -p "Press Enter to retry running Monika..."
            ;;
        [sS])
            "${PYTHON_BIN}" -m cli.main setup
            ;;
        [tT])
            if [ "${CURRENT_TIER}" = "trial" ]; then
                CURRENT_TIER="full"
                export MONIKA_TIER="full"
                unset DATABASE_URL
                unset PAPER_TRADING_MODE
                echo "full" > "${SCRIPT_DIR}/.monika_tier"
                echo "full" > "${AGENT_DIR}/.monika_tier"
                echo "[*] Switched tier to: Full Package."
            else
                CURRENT_TIER="trial"
                export MONIKA_TIER="trial"
                export DATABASE_URL="sqlite+aiosqlite:///data/monika.db"
                export PAPER_TRADING_MODE="true"
                echo "trial" > "${SCRIPT_DIR}/.monika_tier"
                echo "trial" > "${AGENT_DIR}/.monika_tier"
                echo "[*] Switched tier to: Trial Package."
            fi
            ;;
        [qQ])
            echo "[*] Exiting Monika launcher."
            exit ${EXIT_CODE}
            ;;
        *)
            echo "[*] Retrying Monika launch in 3 seconds..."
            sleep 3
            ;;
    esac
done
