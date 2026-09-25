#!/bin/bash

# Navigate to the directory containing this script
cd "$(dirname "$0")"

# ── Baca argumen mode (default: paper) ────────────────────────────────────────
TRADE_MODE="${1:-paper}"
if [[ "$TRADE_MODE" != "paper" && "$TRADE_MODE" != "live" ]]; then
    echo "[ERROR] Mode tidak valid: '$TRADE_MODE'. Gunakan 'paper' atau 'live'."
    exit 1
fi

echo "============================================================"
echo " MONIKA - MT5 Trading Agent"
echo " Mode: $TRADE_MODE"
echo "============================================================"

# Activate virtual environment if present
if [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# ── 1. Buka MT5 Terminal (sekali di awal, TIDAK direstart saat loop) ─────────
MT5_PATH=$(grep -i "^MT5_PATH=" .env 2>/dev/null | head -n1 | cut -d'=' -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'"'"']//' -e 's/["'"'"']$//')
MT5_PID=""

if [[ "$OSTYPE" == "msys"* || "$OSTYPE" == "cygwin"* || "$(uname -s)" == MINGW* || "$(uname -s)" == MSYS* ]]; then
    # Windows native via Git Bash
    if [ -n "$MT5_PATH" ]; then
        MT5_WIN_PATH=$(echo "$MT5_PATH" | tr '/' '\\')
        echo "[1/4] Membuka MetaTrader 5 Terminal: $MT5_WIN_PATH"
        cmd.exe /c start "" "$MT5_WIN_PATH" 2>/dev/null
        echo "[OK] MetaTrader 5 dibuka."
    else
        echo "[1/4] MT5_PATH tidak ditemukan di .env -- lewati."
    fi
else
    # Linux / macOS via Wine
    MT5_UNIX_PATH=$(echo "$MT5_PATH" | tr '\\' '/')
    if [ -n "$MT5_UNIX_PATH" ] && command -v wine &>/dev/null; then
        echo "[1/4] Membuka MetaTrader 5 via Wine: $MT5_UNIX_PATH"
        wine "$MT5_UNIX_PATH" &
        MT5_PID=$!
        echo "[OK] MT5 PID: $MT5_PID"
    elif [ -n "$MT5_UNIX_PATH" ]; then
        echo "[1/4] WARN: MT5_PATH ditemukan tapi Wine tidak tersedia -- lewati."
    else
        echo "[1/4] MT5_PATH tidak ditemukan di .env -- lewati."
    fi
fi

# ── 2. Jalankan 9Router AI Gateway di background ─────────────────────────────
echo "[2/5] Memeriksa dan Menjalankan 9Router AI Gateway (localhost:20128)..."
ROUTER_PID=""
if ! curl -s http://localhost:20128/v1/models >/dev/null 2>&1 && ! nc -z localhost 20128 2>/dev/null; then
    echo "[*] Menjalankan 9Router AI Gateway..."
    if command -v 9router &>/dev/null; then
        9router --no-browser --skip-update &
        ROUTER_PID=$!
    elif command -v npx &>/dev/null; then
        npx -y 9router --no-browser --skip-update &
        ROUTER_PID=$!
    fi
else
    echo "[OK] 9Router AI Gateway sudah aktif di localhost:20128."
fi

# ── 3. Jalankan Dashboard Frontend di background ─────────────────────────────
echo "[3/5] Menjalankan Dashboard Frontend (localhost:5173)..."
(cd logging_observability/dashboard/frontend && npm run dev) &
UI_PID=$!

# Trap SIGINT/SIGTERM: matikan frontend, 9router, dan MT5 Wine saat Ctrl+C
trap "echo 'Stopping all services...'; [ -n \"$UI_PID\" ] && kill $UI_PID 2>/dev/null; [ -n \"$ROUTER_PID\" ] && kill $ROUTER_PID 2>/dev/null; [ -n \"$MT5_PID\" ] && kill $MT5_PID 2>/dev/null; exit" SIGINT SIGTERM

# ── 4. Run database migrations ────────────────────────────────────────────────
echo "[4/5] Checking and running database migrations..."
python -m alembic upgrade head
if [ $? -ne 0 ]; then
    echo "[ERROR] Alembic migration failed! Please check database connection."
    exit 1
fi

# ── 5. Restart-loop: jalankan agent via CLI ───────────────────────────────────
echo "[5/5] Menjalankan Monika via CLI (mode: $TRADE_MODE)..."
while true; do
    echo "Starting AI Trading Agent in $TRADE_MODE mode..."
    if [ "$TRADE_MODE" = "live" ]; then
        python -m cli.main run --mode live --confirm-live
    else
        python -m cli.main run --mode paper
    fi

    EXIT_CODE=$?
    if [ -f "data/clean_shutdown.flag" ]; then
        rm -f "data/clean_shutdown.flag"
        echo "Agent stopped gracefully by operator command. Exiting."
        break
    fi
    echo "Agent exited or crashed (Code $EXIT_CODE). Restarting in 30 seconds..."
    echo "(MT5 Terminal tetap berjalan - tidak perlu restart)"
    sleep 30
done

[ -n "$UI_PID" ] && kill $UI_PID 2>/dev/null
[ -n "$ROUTER_PID" ] && kill $ROUTER_PID 2>/dev/null
