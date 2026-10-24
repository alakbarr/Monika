#!/usr/bin/env bash
# ==============================================================================
# Monika Algorithmic Trading System - Automated Linux VPS Installer
# Designed for clean Ubuntu 22.04 / 24.04 LTS & Debian 11 / 12 systems.
# ==============================================================================

set -euo pipefail

# Text colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

clear 2>/dev/null || true
echo -e "${CYAN}${BOLD}"
echo "======================================================================"
echo "          MONIKA ALGORITHMIC TRADING SYSTEM - VPS SETUP               "
echo "======================================================================"
echo -e "${NC}"
echo -e "Welcome to the automated Monika installation wizard for Linux VPS."
echo -e "This script will inspect your system, configure dependencies, set up"
echo -e "environment secrets, and launch Monika in Docker or standalone mode."
echo ""

# 1. Privilege Check
if [[ $EUID -ne 0 ]]; then
    echo -e "${YELLOW}[!] Note: Running as non-root user. Sudo will be used for system packages.${NC}"
    SUDO="sudo"
else
    SUDO=""
fi

# Detect VPS Public IP
DETECTED_IP=$(curl -s https://api.ipify.org || curl -s https://ifconfig.me || echo "YOUR_VPS_IP")

# 2. Dependency & Docker Verification
echo -e "\n${BLUE}[1/5] Checking system prerequisites and Docker engine...${NC}"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo -e "${GREEN}[OK] Docker and Docker Compose plugin are already installed.${NC}"
else
    echo -e "${YELLOW}[*] Installing essential packages, Docker, and Docker Compose...${NC}"
    $SUDO apt-get update -y
    $SUDO apt-get install -y curl wget git jq ca-certificates gnupg openssl

    echo -e "${YELLOW}[*] Fetching official Docker install script...${NC}"
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    $SUDO sh /tmp/get-docker.sh
    rm -f /tmp/get-docker.sh

    if [[ -n "$SUDO" ]] && [[ -n "${USER:-}" ]]; then
        $SUDO usermod -aG docker "$USER" || true
    fi

    $SUDO systemctl enable --now docker
    echo -e "${GREEN}[OK] Docker successfully installed and service started.${NC}"
fi

# 3. Directory Verification
if [[ ! -f "deploy/docker-compose.vps.yml" ]]; then
    echo -e "${RED}[ERROR] Must be executed from the Monika project root directory.${NC}"
    echo -e "Please run: cd /path/to/monika && bash deploy/install_vps.sh"
    exit 1
fi

# 4. Interactive Configuration Wizard
echo -e "\n${BLUE}[2/5] Configuring Trading Environment & Secrets...${NC}"

ENV_FILE=".env"
if [[ -f "$ENV_FILE" ]]; then
    echo -e "${YELLOW}[i] Existing .env file detected. Missing variables will be appended.${NC}"
else
    if [[ -f ".env.example" ]]; then
        cp .env.example "$ENV_FILE"
        echo -e "${GREEN}[OK] Created .env from .env.example.${NC}"
    else
        touch "$ENV_FILE"
    fi
fi

# Helper function to set or replace env var
set_env_var() {
    local key="$1"
    local value="$2"
    if grep -q "^${key}=" "$ENV_FILE"; then
        # Replace existing key safely
        sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
        echo "${key}=${value}" >> "$ENV_FILE"
    fi
}

# Prompt: Trading Mode
echo ""
echo -e "${BOLD}Select Trading Mode:${NC}"
echo "  1) Paper Trading Sandbox (Safe, simulated funds, recommended for initial VPS test)"
echo "  2) Live MT5 Broker Execution (Connects to live or demo broker account)"
read -rp "Enter choice [1 or 2, default: 1]: " TRADING_MODE_CHOICE
TRADING_MODE_CHOICE=${TRADING_MODE_CHOICE:-1}

if [[ "$TRADING_MODE_CHOICE" == "2" ]]; then
    echo -e "${YELLOW}[!] Live mode selected. Risk limits will be enforced strictly.${NC}"
    set_env_var "PAPER_TRADING_ENABLED" "false"
else
    echo -e "${GREEN}[i] Paper trading selected.${NC}"
    set_env_var "PAPER_TRADING_ENABLED" "true"
fi

# Prompt: Gemini API Key
echo ""
echo -e "${BOLD}AI Brain Configuration (Google Gemini API):${NC}"
EXISTING_GEMINI=$(grep "^GEMINI_API_KEY=" "$ENV_FILE" | cut -d'=' -f2- || true)
if [[ -n "$EXISTING_GEMINI" && "$EXISTING_GEMINI" != "your_gemini_api_key_here" ]]; then
    echo -e "${GREEN}[OK] GEMINI_API_KEY already configured in .env.${NC}"
else
    echo "Enter your Google Gemini API Key (Get a free key at https://aistudio.google.com/):"
    read -rp "GEMINI_API_KEY: " INPUT_GEMINI_KEY
    if [[ -n "$INPUT_GEMINI_KEY" ]]; then
        set_env_var "GEMINI_API_KEY" "$INPUT_GEMINI_KEY"
        echo -e "${GREEN}[OK] GEMINI_API_KEY saved.${NC}"
    else
        echo -e "${YELLOW}[WARN] GEMINI_API_KEY skipped. Monika will operate in local fallback mode until set.${NC}"
    fi
fi

# Prompt: Database Configuration
echo ""
echo -e "${BOLD}Database Configuration:${NC}"
echo "Monika uses PostgreSQL for trade journaling, state persistence, and risk auditing."
echo "Do you already have an existing PostgreSQL DATABASE_URL (e.g. from cloud DB, Supabase, Neon, etc.)?"
read -rp "Use external DATABASE_URL? (y/N): " USE_EXT_DB
USE_EXT_DB=${USE_EXT_DB:-N}

if [[ "$USE_EXT_DB" =~ ^[Yy]$ ]]; then
    read -rp "Enter full async DATABASE_URL (e.g. postgresql+asyncpg://user:pass@host:5432/dbname): " INPUT_DB_URL
    if [[ -n "$INPUT_DB_URL" ]]; then
        set_env_var "DATABASE_URL" "$INPUT_DB_URL"
        set_env_var "COMPOSE_PROFILES" ""
        echo -e "${GREEN}[OK] External DATABASE_URL configured. Local Postgres container will be skipped.${NC}"
    fi
else
    echo -e "${CYAN}[*] Configuring auto-provisioned local PostgreSQL container...${NC}"
    EXISTING_PG_PASS=$(grep "^POSTGRES_PASSWORD=" "$ENV_FILE" | cut -d'=' -f2- || true)
    if [[ -z "$EXISTING_PG_PASS" || "$EXISTING_PG_PASS" == "change_me_to_a_secure_password" ]]; then
        NEW_PG_PASS=$(openssl rand -hex 16 2>/dev/null || tr -dc A-Za-z0-9 </dev/urandom | head -c 24)
        set_env_var "POSTGRES_PASSWORD" "$NEW_PG_PASS"
    fi
    set_env_var "POSTGRES_USER" "monika"
    set_env_var "POSTGRES_DB" "monika_trading"
    set_env_var "COMPOSE_PROFILES" "local-db"
    echo -e "${GREEN}[OK] Local PostgreSQL configured with auto-generated secure credentials.${NC}"
fi

# Synchronize Installation Tier
set_env_var "MONIKA_TIER" "full"
echo "full" > .monika_tier
if [[ ! -f "config/settings.yaml" ]] && [[ -f "config/settings.example.yaml" ]]; then
    cp config/settings.example.yaml config/settings.yaml
fi
if [[ -f "config/settings.yaml" ]]; then
    sed -i "s|^installation_tier:.*|installation_tier: full|" config/settings.yaml 2>/dev/null || true
fi

# Prompt: Telegram Notifications
echo ""
echo -e "${BOLD}Telegram Notifications (Optional):${NC}"
read -rp "Enable Telegram alerts for trade executions & risk alerts? (y/N): " ENABLE_TG
if [[ "$ENABLE_TG" =~ ^[Yy]$ ]]; then
    read -rp "Enter Telegram Bot Token: " TG_TOKEN
    read -rp "Enter Telegram Chat ID: " TG_CHAT_ID
    if [[ -n "$TG_TOKEN" && -n "$TG_CHAT_ID" ]]; then
        set_env_var "TELEGRAM_BOT_TOKEN" "$TG_TOKEN"
        set_env_var "TELEGRAM_CHAT_ID" "$TG_CHAT_ID"
        echo -e "${GREEN}[OK] Telegram credentials saved.${NC}"
        # Test Ping
        echo -e "${CYAN}[*] Sending welcome verification test message to Telegram...${NC}"
        TEST_MSG="🚀 Monika Algorithmic Trading successfully initialized on Linux VPS ($DETECTED_IP)!"
        curl -s -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
            -d "chat_id=${TG_CHAT_ID}" \
            -d "text=${TEST_MSG}" >/dev/null 2>&1 || true
        echo -e "${GREEN}[OK] Telegram test ping sent.${NC}"
    fi
fi

# Dashboard Security Key
echo ""
echo -e "${BOLD}Dashboard Web Security:${NC}"
EXISTING_DASH_KEY=$(grep "^DASHBOARD_API_KEY=" "$ENV_FILE" | cut -d'=' -f2- || true)
if [[ -z "$EXISTING_DASH_KEY" || "$EXISTING_DASH_KEY" == "change_me_to_a_random_token" ]]; then
    NEW_DASH_KEY=$(openssl rand -hex 16 2>/dev/null || tr -dc A-Za-z0-9 </dev/urandom | head -c 24)
    set_env_var "DASHBOARD_API_KEY" "$NEW_DASH_KEY"
    EXISTING_DASH_KEY="$NEW_DASH_KEY"
fi
set_env_var "DASHBOARD_BIND_IP" "0.0.0.0"
echo -e "${GREEN}[OK] Dashboard secured with access token: ${BOLD}${EXISTING_DASH_KEY}${NC}"

# 5. Build and Launch
echo -e "\n${BLUE}[3/5] Starting Monika Services via Docker Compose...${NC}"

# Build application image if needed and start containers
docker compose -f deploy/docker-compose.vps.yml --project-directory . build agent
docker compose -f deploy/docker-compose.vps.yml --project-directory . up -d

echo -e "\n${BLUE}[4/5] Checking container health...${NC}"
sleep 5
docker compose -f deploy/docker-compose.vps.yml --project-directory . ps

# 6. Final Summary
echo -e "\n${GREEN}${BOLD}"
echo "======================================================================"
echo "          MONIKA IS NOW RUNNING ON YOUR LINUX VPS!                    "
echo "======================================================================"
echo -e "${NC}"
echo -e "Web Dashboard URL:    ${CYAN}${BOLD}http://${DETECTED_IP}:8000${NC}"
echo -e "Dashboard API Key:    ${YELLOW}${BOLD}${EXISTING_DASH_KEY}${NC}"
echo ""
echo -e "${BOLD}Management Cheat Sheet:${NC}"
echo -e "  * View Live Logs:   ${CYAN}docker compose -f deploy/docker-compose.vps.yml logs -f agent${NC}"
echo -e "  * Restart Agent:    ${CYAN}docker compose -f deploy/docker-compose.vps.yml restart agent${NC}"
echo -e "  * Stop Services:    ${CYAN}docker compose -f deploy/docker-compose.vps.yml down${NC}"
echo -e "  * Emergency Stop:   ${RED}curl -X POST http://localhost:8000/api/v1/kill -H \"X-API-Key: ${EXISTING_DASH_KEY}\"${NC}"
echo ""
echo -e "${GREEN}Installation completed successfully.${NC}\n"
