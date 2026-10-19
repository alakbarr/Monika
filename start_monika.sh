#!/usr/bin/env bash
# ==============================================================================
# Monika — Autonomous MT5 Trading Agent Production Entrypoint
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

export PYTHONPATH="${SCRIPT_DIR}/src:${PYTHONPATH}"
export PYTHONUNBUFFERED=1

# Resolve python interpreter (prefer venv if active or present)
PYTHON_BIN="python"
if [ -f "${SCRIPT_DIR}/venv/bin/python" ]; then
    PYTHON_BIN="${SCRIPT_DIR}/venv/bin/python"
elif [ -f "${SCRIPT_DIR}/.venv/bin/python" ]; then
    PYTHON_BIN="${SCRIPT_DIR}/.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
fi

# Ensure required directories exist
mkdir -p "${SCRIPT_DIR}/logs" "${SCRIPT_DIR}/data"

echo "[Monika] Launching trading agent via ${PYTHON_BIN}..."
exec "${PYTHON_BIN}" -m monika.interfaces.cli.main run "$@"
