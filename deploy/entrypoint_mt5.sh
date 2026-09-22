#!/bin/bash
# ==============================================================================
# Monika — MT5 Wine Container Entrypoint
# Initializes virtual X11 display (Xvfb) and launches terminal64.exe under Wine
# ==============================================================================

set -e

echo "[MT5-Wine] Starting virtual display on :99..."
Xvfb :99 -screen 0 1024x768x16 &
XVFB_PID=$!

sleep 2

echo "[MT5-Wine] Initializing Wine prefix..."
wineboot --init || true

echo "[MT5-Wine] Shared bridge available at /shared/mt5_bridge"

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
