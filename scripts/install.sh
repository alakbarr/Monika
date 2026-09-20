#!/usr/bin/env bash
# ==============================================================================
# Monika (MT5 Trading Agent) - Linux VPS One-Click Installer
# ==============================================================================

set -e

echo "============================================================"
echo " Monika: Institutional Trading Agent - Linux Installer      "
echo "============================================================"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
AGENT_DIR="$ROOT_DIR/trading-agent"
VENV_DIR="$AGENT_DIR/venv"
PYTHON_BIN="$VENV_DIR/bin/python"

# 1. System prerequisites
echo ""
echo "[1/5] Checking Python 3.10+ installation..."
if ! command -v python3 &>/dev/null; then
    echo "Error: Python 3 is required. Run: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Detected Python $PY_VER"

# 2. Setup Virtual Environment
echo ""
echo "[2/5] Setting up virtual environment in $VENV_DIR..."
if [ ! -f "$PYTHON_BIN" ]; then
    python3 -m venv "$VENV_DIR"
    echo "Virtual environment created."
else
    echo "Existing virtual environment found."
fi

# 3. Fast installation with uv if available, or pip
echo ""
echo "[3/5] Installing core dependencies..."
if command -v uv &>/dev/null; then
    echo "Using fast uv installer..."
    uv pip install -r "$AGENT_DIR/requirements.txt" --python "$PYTHON_BIN"
else
    echo "Using pip installer..."
    "$PYTHON_BIN" -m pip install --upgrade pip
    "$PYTHON_BIN" -m pip install -r "$AGENT_DIR/requirements.txt"
fi

# 4. Check configuration
echo ""
echo "[4/5] Checking environment configuration..."
if [ ! -f "$ROOT_DIR/.env" ] && [ -f "$ROOT_DIR/.env.example" ]; then
    cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
    echo "Created .env from .env.example."
else
    echo "Configuration file (.env) already present."
fi

# 5. Run setup doctor
echo ""
echo "[5/5] Running environment doctor..."
cd "$AGENT_DIR"
"$PYTHON_BIN" -m cli.main doctor || true

echo ""
echo "============================================================"
echo " Installation Complete! Run 'bash trading-agent/start_agent.sh'"
echo "============================================================"
