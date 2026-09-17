import os
from dotenv import dotenv_values

REQUIRED = [
    "ANTHROPIC_API_KEY", "DATABASE_URL", "MT5_ACCOUNT", 
    "MT5_PASSWORD", "MT5_SERVER", "MT5_PATH", 
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_ADMIN_CHAT_ID",
    "GEMINI_PAID_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"
]
RECOMMENDED = ["GEMINI_API_KEY", "GEMINI_API_KEYS", "GROQ_API_KEYS", "FRED_API_KEY", "FINNHUB_API_KEY"]
OPTIONAL = ["EIA_API_KEY", "DASHBOARD_PORT", "MT5_COMMON_FILES_PATH", "TELEGRAM_ALLOWED_USERS"]

def check_keys():
    root_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    agent_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading-agent", ".env")
    
    if os.path.exists(root_env):
        env_path = root_env
    elif os.path.exists(agent_env):
        env_path = agent_env
    else:
        print("File .env tidak ditemukan!")
        return

    print(f"Membaca dari: {env_path}\n")
    keys = set(dotenv_values(env_path).keys())
    
    print("=== REQUIRED ===")
    for k in REQUIRED:
        print(f"[{'X' if k in keys else ' '}] {k}")
        
    print("\n=== RECOMMENDED ===")
    for k in RECOMMENDED:
        print(f"[{'X' if k in keys else ' '}] {k}")
        
    print("\n=== OPTIONAL ===")
    for k in OPTIONAL:
        print(f"[{'X' if k in keys else ' '}] {k}")

if __name__ == "__main__":
    check_keys()
