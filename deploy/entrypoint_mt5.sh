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

# If mt5server.exe is present, start the RPC bridge for Linux Python
if [ -f "/opt/mt5/mt5server.exe" ]; then
    echo "[MT5-Wine] Starting mt5server.exe RPC bridge on port 18812..."
    wine /opt/mt5/mt5server.exe -p 18812 &
elif [ -f "/wine/mt5server.exe" ]; then
    echo "[MT5-Wine] Starting /wine/mt5server.exe RPC bridge on port 18812..."
    wine /wine/mt5server.exe -p 18812 &
else
    echo "[MT5-Wine] Notice: mt5server.exe not found in /opt/mt5 or /wine. If using mt5linux RPC bridge, mount mt5server.exe into /opt/mt5."
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
