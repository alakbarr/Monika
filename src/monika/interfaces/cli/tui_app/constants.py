# ==============================================================================
# File: interfaces/cli/tui_app/constants.py
# Description: Constants and defaults for Monika TUI Terminal Dashboard
# ==============================================================================

import os
from typing import List, Tuple

DEFAULT_API_URL: str = (
    os.environ.get("MONIKA_API_URL")
    or os.environ.get("TRADEAGENT_API_URL")
    or os.environ.get("DASHBOARD_URL")
    or "http://127.0.0.1:8000"
)

COMMAND_SUGGESTIONS: List[str] = [
    "status",
    "pause",
    "resume",
    "kill",
    "chat",
    "refresh",
    "config",
    "theme",
    "steer",
    "queue",
    "dequeue",
    "sessions",
    "logs",
    "clear",
    "help",
    "quit",
]

DETERMINISTIC_RISK_CHECKS: List[Tuple[str, str, str, str]] = [
    ("Daily Trade Count", "0 trades", "≤ 10 / day", "PASS"),
    ("Trading Not Paused", "Active", "Emergency Pause = False", "PASS"),
    ("Edge Status Not Paused", "Valid Edge", "Min WR 50%, Exp > 0", "PASS"),
    ("VIX Volatility Threshold", "16.5", "≤ 32.0 (Extreme Volatility)", "PASS"),
    ("Flash Crash Cooldown", "Normal", "15m Post-Spike Lockout", "PASS"),
    ("Sizing Valid", "0.01 - 5.0 lots", "Non-Zero Valid Lots", "PASS"),
    ("Lot Size Limit", "1.0 lot max", "Account Tier Capped", "PASS"),
    ("Daily Drawdown", "0.00%", "≤ 3.0% Max Daily Loss", "PASS"),
    ("Weekly Drawdown", "0.00%", "≤ 6.0% Max Weekly Loss", "PASS"),
    ("Max Concurrent Positions", "0 open", "≤ 5 Simultaneous Positions", "PASS"),
    ("No Duplicate Symbol", "None", "1 Position / Pair Max", "PASS"),
    ("Portfolio Heat", "0.00%", "≤ 6.0% Total Equity at Risk", "PASS"),
    ("Weekend Proximity", "Mid-week", "Friday 20:00 UTC Close Gate", "PASS"),
    ("Rollover Window", "Clear", "21:55-22:15 UTC Spread Lock", "PASS"),
    ("Post-SL Cooldown", "Clear", "30m Loss Quarantine", "PASS"),
    ("News Window Filter", "Clear", "±15m High-Impact Red Folder", "PASS"),
    ("Correlation Exposure", "0.00", "Max 0.70 Pair Correlation", "PASS"),
    ("Consecutive Losses", "0 losses", "Max 3 Streak Loss Limit", "PASS"),
    ("Data Freshness", "Live", "≤ 60s Quote Latency", "PASS"),
    ("TimesFM Expectancy", "+0.45R", "Directional Forecast ≥ 0", "PASS"),
    ("Schmitt Regime Filter", "Trend/Range", "Valid Market State", "PASS"),
    ("VPIN Toxicity Filter", "0.18", "≤ 0.55 Toxic Order Flow", "PASS"),
]
