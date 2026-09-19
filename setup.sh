#!/usr/bin/env bash
set -e

# ============================================================
#   MONIKA - Autonomous MT5 Trading Agent Setup Bootstrapper
# ============================================================

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="${ROOT_DIR}/trading-agent"

echo "============================================================"
echo "  MONIKA - Autonomous MT5 Trading Agent Setup Bootstrapper"
echo "============================================================"
echo ""

# 1. Check Python
echo "[1/5] Checking Python 3.11+..."
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 is not installed or not in PATH."
    exit 1
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "[OK] Python ${PY_VER} detected."

# 2. Setup Virtual Environment
echo ""
echo "[2/5] Setting up virtual environment..."
if [ ! -f "${AGENT_DIR}/venv/bin/python" ]; then
    echo "Creating virtual environment at ${AGENT_DIR}/venv..."
    python3 -m venv "${AGENT_DIR}/venv"
    echo "[OK] Virtual environment created."
else
    echo "[OK] Virtual environment already exists."
fi

source "${AGENT_DIR}/venv/bin/activate"

# 3. Install Python Dependencies
echo ""
echo "[3/5] Installing core dependencies..."
pip install --upgrade pip >/dev/null 2>&1
pip install -r "${AGENT_DIR}/requirements.txt"
echo "[OK] Python dependencies installed."

# 4. Environment File Initialization
echo ""
echo "[4/5] Checking environment configuration..."
if [ ! -f "${ROOT_DIR}/.env" ]; then
    if [ -f "${ROOT_DIR}/.env.example" ]; then
        cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
        chmod 600 "${ROOT_DIR}/.env"
        echo "[OK] Initialized .env from .env.example with secure permissions."
    fi
else
    echo "[OK] .env already exists."
fi

# 5. Install Frontend Dependencies if Node is present
echo ""
echo "[5/5] Checking dashboard frontend dependencies..."
if command -v npm &>/dev/null; then
    if [ ! -d "${AGENT_DIR}/logging_observability/dashboard/frontend/node_modules" ]; then
        echo "Installing Vite/React dashboard dependencies..."
        (cd "${AGENT_DIR}/logging_observability/dashboard/frontend" && npm install --silent)
        echo "[OK] Dashboard frontend dependencies installed."
    else
        echo "[OK] Dashboard frontend dependencies already installed."
    fi
else
    echo "[INFO] npm not detected. Skipping dashboard build for now."
fi

echo ""
echo "============================================================"
echo "  Dependencies ready. Launching Monika Interactive Setup..."
echo "============================================================"
echo ""

cd "${AGENT_DIR}"
export PYTHONPATH="${AGENT_DIR}"
python3 -m cli.main setup

echo ""
echo "Setup completed. Start Monika anytime with: bash trading-agent/start_agent.sh"
