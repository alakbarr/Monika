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
PYTHON_BIN="C:\\Python311\\python.exe"
if wine "$PYTHON_BIN" --version &>/dev/null; then
    echo "[MT5-Wine] Starting Wine Python RPyC bridge on 0.0.0.0:18812..."
    wine "$PYTHON_BIN" -m rpyc.cli.rpyc_classic --host 0.0.0.0 --port 18812 &
elif wine python --version &>/dev/null; then
    echo "[MT5-Wine] Starting Wine Python RPyC bridge on 0.0.0.0:18812..."
    wine python -m rpyc.cli.rpyc_classic --host 0.0.0.0 --port 18812 &
fi

# Determine terminal64.exe path (mounted /opt/mt5 or internal Wine installation)
MT5_EXE=""
if [ -f "/opt/mt5/terminal64.exe" ]; then
    MT5_EXE="/opt/mt5/terminal64.exe"
elif [ -f "${WINEPREFIX}/drive_c/Program Files/MetaTrader 5/terminal64.exe" ]; then
    MT5_EXE="${WINEPREFIX}/drive_c/Program Files/MetaTrader 5/terminal64.exe"
elif [ "${AUTO_INSTALL_MT5:-true}" = "true" ]; then
    echo "[MT5-Wine] /opt/mt5/terminal64.exe not found. Attempting silent download & installation of MetaTrader 5..."
    if curl -fsSL -o /tmp/mt5setup.exe https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe; then
        echo "[MT5-Wine] Running silent installer via Wine..."
        wine /tmp/mt5setup.exe /auto || true
        sleep 5
        rm -f /tmp/mt5setup.exe
        if [ -f "${WINEPREFIX}/drive_c/Program Files/MetaTrader 5/terminal64.exe" ]; then
            MT5_EXE="${WINEPREFIX}/drive_c/Program Files/MetaTrader 5/terminal64.exe"
            echo "[MT5-Wine] MetaTrader 5 installed successfully at ${MT5_EXE}"
        fi
    else
        echo "[MT5-Wine] Notice: Failed to download mt5setup.exe (network offline or restricted)."
    fi
fi

# If terminal64.exe is resolved, launch it
if [ -n "$MT5_EXE" ] && [ -f "$MT5_EXE" ]; then
    echo "[MT5-Wine] Launching MetaTrader 5 terminal: ${MT5_EXE}..."
    wine "$MT5_EXE" /portable &
    MT5_PID=$!
    wait $MT5_PID
else
    echo "[MT5-Wine] Notice: MetaTrader 5 terminal executable not found. Running headless bridge standby mode."
    tail -f /dev/null
fi
