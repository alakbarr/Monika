#!/usr/bin/env bash
echo "============================================================"
echo "  MONIKA - Setup is now unified into start_monika.sh!"
echo "============================================================"
echo ""
echo "[*] Redirecting to ./start_monika.sh (single launcher for setup & run)..."
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/start_monika.sh" "$@"
