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

# ── 1. Kompilasi EA & Buka MT5 Terminal (sekali di awal) ────────────────────
MT5_PATH=$(grep -i "^MT5_PATH=" .env 2>/dev/null | head -n1 | cut -d'=' -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'"'"']//' -e 's/["'"'"']$//')
MT5_PID=""

# Kompilasi AIAgent_EA.mq5 jika file tersedia
EA_SOURCE="execution/ea_bridge/AIAgent_EA.mq5"
if [ -f "$EA_SOURCE" ]; then
    echo "[1/5] Memeriksa & mengompilasi AIAgent_EA.mq5..."
    if [[ "$OSTYPE" == "msys"* || "$OSTYPE" == "cygwin"* || "$(uname -s)" == MINGW* || "$(uname -s)" == MSYS* ]]; then
        METAEDITOR_CMD=""
        if [ -n "$MT5_PATH" ]; then
            MT5_DIR=$(dirname "$MT5_PATH")
            if [ -f "$MT5_DIR/metaeditor64.exe" ]; then
                METAEDITOR_CMD="$MT5_DIR/metaeditor64.exe"
            fi
        fi
        if [ -z "$METAEDITOR_CMD" ]; then
            for candidate in "/c/Program Files/FBS MetaTrader 5/metaeditor64.exe" "/c/Program Files/MetaTrader 5/metaeditor64.exe"; do
                if [ -f "$candidate" ]; then
                    METAEDITOR_CMD="$candidate"
                    break
                fi
            done
        fi

        if [ -n "$METAEDITOR_CMD" ]; then
            WIN_EA_PATH="$(pwd -W 2>/dev/null || pwd)/$EA_SOURCE"
            WIN_EA_PATH=$(echo "$WIN_EA_PATH" | tr '/' '\\')
            WIN_META=$(echo "$METAEDITOR_CMD" | sed -e 's|^/c/|C:\\|' -e 's|/|\\|g')
            cmd.exe /c "\"$WIN_META\" /compile:\"$WIN_EA_PATH\" /log:\"$(dirname "$WIN_EA_PATH")\\compile.log\"" >/dev/null 2>&1
            if [ -f "execution/ea_bridge/AIAgent_EA.ex5" ]; then
                echo "[OK] AIAgent_EA.ex5 siap digunakan."
                rm -f "execution/ea_bridge/compile.log" 2>/dev/null
            else
                echo "[WARN] Kompilasi AIAgent_EA.mq5 gagal. Cek execution/ea_bridge/compile.log"
            fi
        else
            echo "[WARN] metaeditor64.exe tidak ditemukan -- lewati kompilasi EA."
        fi
    elif [ -n "$MT5_PATH" ] && command -v wine &>/dev/null; then
        MT5_DIR=$(dirname "$MT5_PATH")
        if [ -f "$MT5_DIR/metaeditor64.exe" ]; then
            wine "$MT5_DIR/metaeditor64.exe" /compile:"$EA_SOURCE" >/dev/null 2>&1
            [ -f "execution/ea_bridge/AIAgent_EA.ex5" ] && echo "[OK] AIAgent_EA.ex5 siap digunakan (Wine)."
        fi
    fi
fi

if [[ "$OSTYPE" == "msys"* || "$OSTYPE" == "cygwin"* || "$(uname -s)" == MINGW* || "$(uname -s)" == MSYS* ]]; then
    # Windows native via Git Bash
    if [ -n "$MT5_PATH" ]; then
        MT5_WIN_PATH=$(echo "$MT5_PATH" | tr '/' '\\')
        echo "[*] Membuka MetaTrader 5 Terminal: $MT5_WIN_PATH"
        cmd.exe //c start "\"\"" "$MT5_WIN_PATH" 2>/dev/null
        echo "[OK] MetaTrader 5 dibuka."
    else
        echo "[*] MT5_PATH tidak ditemukan di .env -- lewati."
    fi
else
    # Linux / macOS via Wine
    MT5_UNIX_PATH=$(echo "$MT5_PATH" | tr '\\' '/')
    if [ -n "$MT5_UNIX_PATH" ] && command -v wine &>/dev/null; then
        echo "[*] Membuka MetaTrader 5 via Wine: $MT5_UNIX_PATH"
        wine "$MT5_UNIX_PATH" &
        MT5_PID=$!
        echo "[OK] MT5 PID: $MT5_PID"
    elif [ -n "$MT5_UNIX_PATH" ]; then
        echo "[*] WARN: MT5_PATH ditemukan tapi Wine tidak tersedia -- lewati."
    else
        echo "[*] MT5_PATH tidak ditemukan di .env -- lewati."
    fi
fi

# ── 2 & 3. 9Router & Dashboard Frontend ─────────────────────────────────────
ROUTER_PID=""
UI_PID=""
if [ "${MONIKA_EXTERNAL_SERVICES:-0}" = "1" ]; then
    echo "[2/5] [INFO] 9Router AI Gateway dikelola di tab terpisah (localhost:20128)."
    echo "[3/5] [INFO] Dashboard Frontend dikelola di tab terpisah (localhost:5173)."
else
    echo "[2/5] Memeriksa dan Menjalankan 9Router AI Gateway (localhost:20128)..."
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

    echo "[3/5] Menjalankan Dashboard Frontend (localhost:5173)..."
    (cd logging_observability/dashboard/frontend && npm run dev) &
    UI_PID=$!
fi

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
