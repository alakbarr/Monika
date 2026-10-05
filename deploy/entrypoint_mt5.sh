#!/bin/bash
# ==============================================================================
# Monika — MT5 Wine Container Entrypoint
# Initializes virtual X11 display (Xvfb) and launches terminal64.exe under Wine
# along with MT5 Linux RPC Server (mt5server / RPyC bridge) on port 18812
# ==============================================================================

set -e

echo "[MT5-Wine] Starting virtual display on :99..."
Xvfb :99 -screen 0 1024x768x16 &
XVFB_PID=$!

sleep 2

echo "[MT5-Wine] Initializing Wine prefix..."
wineboot --init || true

echo "[MT5-Wine] Shared bridge available at /shared/mt5_bridge"

# Launch MT5 RPyC classic bridge if Wine Python is available
if command -v wine &>/dev/null; then
    if wine python --version &>/dev/null; then
        echo "[MT5-Wine] Starting Wine Python RPyC bridge on port 18812..."
        wine python -m rpyc.cli.rpyc_classic --port 18812 &
    fi
fi

# If terminal64.exe is mounted or present, launch it
if [ -f "/opt/mt5/terminal64.exe" ]; then
    echo "[MT5-Wine] Launching MetaTrader 5 terminal64.exe..."
    wine /opt/mt5/terminal64.exe /portable &
    MT5_PID=$!
    wait $MT5_PID
else
    echo "[MT5-Wine] Notice: /opt/mt5/terminal64.exe not found. Running headless bridge standby mode."
    tail -f /dev/null
fi
