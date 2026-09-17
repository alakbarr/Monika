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

# ── 1. Buka MT5 Terminal via Wine (sekali di awal, TIDAK direstart saat loop) ─
MT5_PATH=$(grep -i "^MT5_PATH=" .env 2>/dev/null | head -n1 | cut -d'=' -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'"'"']//' -e 's/["'"'"']$//' | tr '\\' '/')
MT5_PID=""
if [ -n "$MT5_PATH" ] && command -v wine &>/dev/null; then
    echo "[1/4] Membuka MetaTrader 5 via Wine: $MT5_PATH"
    wine "$MT5_PATH" &
    MT5_PID=$!
    echo "[OK] MT5 PID: $MT5_PID"
elif [ -n "$MT5_PATH" ]; then
    echo "[1/4] WARN: MT5_PATH ditemukan tapi Wine tidak tersedia -- lewati."
else
    echo "[1/4] MT5_PATH tidak ditemukan di .env -- lewati."
fi

# ── 2. Jalankan Dashboard Frontend di background ─────────────────────────────
echo "[2/4] Menjalankan Dashboard Frontend (localhost:5173)..."
(cd logging_observability/dashboard/frontend && npm run dev) &
UI_PID=$!

# Trap SIGINT/SIGTERM: matikan frontend dan MT5 Wine saat Ctrl+C
trap "echo 'Stopping all services...'; kill $UI_PID 2>/dev/null; [ -n \"$MT5_PID\" ] && kill $MT5_PID 2>/dev/null; exit" SIGINT SIGTERM

# ── 3. Run database migrations ────────────────────────────────────────────────
echo "[3/4] Checking and running database migrations..."
python -m alembic upgrade head
if [ $? -ne 0 ]; then
    echo "[ERROR] Alembic migration failed! Please check database connection."
    exit 1
fi

# ── 4. Restart-loop: jalankan agent via CLI ───────────────────────────────────
echo "[4/4] Menjalankan Monika via CLI (mode: $TRADE_MODE)..."
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

kill $UI_PID 2>/dev/null
