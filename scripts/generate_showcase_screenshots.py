#!/usr/bin/env python3
"""
scripts/generate_showcase_screenshots.py
Automated screenshot generator for Monika AI Trading Agent showcase.
Runs an ephemeral FastAPI mock server serving live-accurate September 2026 market data
and captures 10 high-resolution screenshots for GitHub README documentation.
"""

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Setup paths
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "trading-agent"))

DOCS_IMG_DIR = ROOT_DIR / "docs" / "images"
DOCS_IMG_DIR.mkdir(parents=True, exist_ok=True)
FRONTEND_DIST = ROOT_DIR / "trading-agent" / "logging_observability" / "dashboard" / "frontend" / "dist"

CHROME_PATH = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
if not CHROME_PATH.exists():
    CHROME_PATH = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")

PORT = 8899
BASE_URL = f"http://127.0.0.1:{PORT}"

# Real-time September 2026 market quotes (queried directly from active MT5)
MARKET_QUOTES = {
    "XAUUSD": {"bid": 4360.31, "ask": 4360.68, "spread": 0.37, "chgPct": 0.85, "high": 4378.50, "low": 4338.20, "name": "Gold Spot / US Dollar"},
    "EURUSD": {"bid": 1.14766, "ask": 1.14777, "spread": 1.1, "chgPct": -0.22, "high": 1.15120, "low": 1.14610, "name": "Euro vs US Dollar"},
    "GBPUSD": {"bid": 1.33495, "ask": 1.33506, "spread": 1.1, "chgPct": 0.14, "high": 1.33850, "low": 1.33280, "name": "British Pound vs USD"},
    "USDJPY": {"bid": 155.998, "ask": 156.008, "spread": 1.0, "chgPct": 0.48, "high": 156.450, "low": 155.320, "name": "US Dollar vs Yen"},
    "BTCUSD": {"bid": 76756.8, "ask": 76776.45, "spread": 19.65, "chgPct": 1.85, "high": 77400.0, "low": 75280.0, "name": "Bitcoin Spot Index"},
    "AUDUSD": {"bid": 0.71125, "ask": 0.71136, "spread": 1.1, "chgPct": -0.15, "high": 0.71450, "low": 0.70980, "name": "Australian Dollar vs USD"},
    "XTIUSD": {"bid": 97.24, "ask": 97.26, "spread": 0.02, "chgPct": 2.40, "high": 98.60, "low": 95.80, "name": "WTI Crude Oil Spot"},
    "XBRUSD": {"bid": 101.05, "ask": 101.07, "spread": 0.02, "chgPct": 2.15, "high": 102.40, "low": 99.50, "name": "Brent Crude Oil Spot"},
}

app = FastAPI(title="Showcase Mock Server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/ping")
async def ping():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/auth/role")
async def auth_role():
    return {"role": "admin", "is_localhost": True}


@app.get("/api/health")
@app.get("/api/health/diagnostics")
async def health():
    return {
        "status": "ok",
        "uptime_seconds": 128450,
        "db_connected": True,
        "mt5_connected": True,
        "heartbeat_age_seconds": 14,
        "last_scraper_run": "2026-09-18T00:15:00Z",
        "last_analysis_cycle": "2026-09-18T00:30:00Z",
        "gemini_api_available": True,
        "gemini_quota": {
            "flash": {"used": 155, "remaining": 845, "max_rpd": 1000},
            "flash_lite": {"used": 80, "remaining": 920, "max_rpd": 1000},
        },
        "data_freshness": {
            "news_hours_old": 0.2,
            "calendar_hours_old": 0.5,
            "vix_days_old": 0,
            "cot_days_old": 1,
        },
        "api_cost_ytd_usd": 24.80,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/overview")
async def overview():
    return {
        "agent_status": "active",
        "open_positions_count": 3,
        "daily_pnl": 842.00,
        "daily_pnl_pct": 8.42,
        "current_drawdown": 85.00,
        "drawdown_pct": 0.85,
        "trading_paused": False,
        "pause_reason": None,
        "vix": 15.82,
        "vix_date": "2026-09-18T00:00:00Z",
        "last_analysis_at": "2026-09-18T00:30:00Z",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/positions")
@app.get("/api/positions/all")
@app.get("/api/trading/positions")
@app.get("/api/trading/positions/all")
async def positions():
    # Return direct list as frontend Position[]
    return [
        {
            "id": 101,
            "mt5_ticket": 8921041,
            "symbol": "XAUUSD",
            "direction": "buy",
            "volume": 0.05,
            "entry_price": 4345.20,
            "current_price": 4360.50,
            "sl": 4330.00,
            "tp": 4385.00,
            "pnl": 306.00,
            "floating_pnl": 306.00,
            "opened_at": "2026-09-17T22:55:00Z",
            "closed_at": None,
            "status": "open",
        },
        {
            "id": 102,
            "mt5_ticket": 8921055,
            "symbol": "EURUSD",
            "direction": "sell",
            "volume": 0.20,
            "entry_price": 1.14950,
            "current_price": 1.14770,
            "sl": 1.15250,
            "tp": 1.14200,
            "pnl": 36.00,
            "floating_pnl": 36.00,
            "opened_at": "2026-09-17T21:30:00Z",
            "closed_at": None,
            "status": "open",
        },
        {
            "id": 103,
            "mt5_ticket": 8921072,
            "symbol": "BTCUSD",
            "direction": "buy",
            "volume": 0.02,
            "entry_price": 75800.0,
            "current_price": 76760.0,
            "sl": 74600.0,
            "tp": 78500.0,
            "pnl": 96.00,
            "floating_pnl": 96.00,
            "opened_at": "2026-09-17T20:18:00Z",
            "closed_at": None,
            "status": "open",
        },
    ]


@app.get("/api/activity")
@app.get("/api/trading/activity")
async def activity():
    # Return direct list as frontend ActivityLog[]
    return [
        {"id": 1, "timestamp": "2026-09-18T00:38:12Z", "category": "trading", "description": "MT5 Ticket #8921041 trailing stop adjusted to $4,348.00 (Locked Profit +$140.00)", "actor": "TrailingStopManager", "related_id": 8921041},
        {"id": 2, "timestamp": "2026-09-18T00:30:45Z", "category": "analysis", "description": "Cycle #847 synthesis completed: Adjudicated BUY bias for XAUUSD (Confidence 84.5%)", "actor": "MarketAwareJudge", "related_id": None},
        {"id": 3, "timestamp": "2026-09-18T00:28:10Z", "category": "risk", "description": "RiskGate verification PASSED: Portfolio VaR at 1.18%, Daily Drawdown at 0.85% (Limit: 3.0%)", "actor": "RiskGate", "related_id": None},
        {"id": 4, "timestamp": "2026-09-18T00:25:30Z", "category": "analysis", "description": "Debate arbitration concluded: Bull Thesis prevailed over Bear Dissent (Confluence 8/10)", "actor": "DebateArbitrator", "related_id": None},
        {"id": 5, "timestamp": "2026-09-18T00:15:02Z", "category": "analysis", "description": "Macro Brief archived: Post-FOMC rate hike 4.00% analysis digested into LLM context", "actor": "FundamentalSynthesizer", "related_id": None},
        {"id": 6, "timestamp": "2026-09-18T00:05:18Z", "category": "risk", "description": "PositionGuardian routine check: All 3 active tickets healthy, zero news blackout violations", "actor": "PositionGuardian", "related_id": None},
        {"id": 7, "timestamp": "2026-09-17T23:55:00Z", "category": "system", "description": "AIAgent_EA heartbeat ping acknowledged (Roundtrip latency: 18ms)", "actor": "EABridge", "related_id": None},
        {"id": 8, "timestamp": "2026-09-17T23:42:15Z", "category": "analysis", "description": "TimesFM 3.0 inference: Projected XAUUSD Daily Range H:4382.00 / L:4335.50", "actor": "TimesFM", "related_id": None},
        {"id": 9, "timestamp": "2026-09-17T23:30:00Z", "category": "trading", "description": "TriggerChecker: Evaluated 4 active conditional triggers, 0 threshold breaches", "actor": "TriggerChecker", "related_id": None},
        {"id": 10, "timestamp": "2026-09-17T23:15:22Z", "category": "system", "description": "Prompt cache checkpoint saved: 79.4% cache hit rate achieved across last 24h", "actor": "TokenAuditor", "related_id": None},
    ]


@app.get("/api/analysis")
@app.get("/api/analyses")
@app.get("/api/trading/analysis")
@app.get("/api/trading/analyses")
async def analyses():
    # Return direct list as frontend Analysis[]
    return [
        {
            "id": 1,
            "symbol": "XAUUSD",
            "decision": "buy",
            "confidence": 0.86,
            "generated_at": "2026-09-18T00:30:00Z",
            "stop_loss": 4330.00,
            "take_profit": 4385.00,
            "rationale": "Gold supercycle continuation. Sustained demand post-FOMC hike defying high yields. SMC Order block holding firmly at 4342 with institutional buy-side liquidity absorption.",
            "reevaluation_trigger": "Price drops below 4335 or VIX spikes > 22",
            "invalidation": "4328.00 structural break",
        },
        {
            "id": 2,
            "symbol": "EURUSD",
            "decision": "sell",
            "confidence": 0.78,
            "generated_at": "2026-09-18T00:25:00Z",
            "stop_loss": 1.1525,
            "take_profit": 1.1420,
            "rationale": "Euro faces heavy pressure against broad DXY strength after Fed 4.00% terminal rate adjustment. Overhead supply zone active near 1.1495.",
            "reevaluation_trigger": "Eurozone CPI surprise > 2.6%",
            "invalidation": "1.1530 resistance reclaim",
        },
        {
            "id": 3,
            "symbol": "USDJPY",
            "decision": "buy",
            "confidence": 0.82,
            "generated_at": "2026-09-18T00:22:00Z",
            "stop_loss": 155.20,
            "take_profit": 156.80,
            "rationale": "US-Japan interest rate divergence widening. Bullish trend structure confirmed with pullback buy setups near 155.80 support.",
            "reevaluation_trigger": "BoJ surprise verbal intervention",
            "invalidation": "154.90 break",
        },
        {
            "id": 4,
            "symbol": "BTCUSD",
            "decision": "buy",
            "confidence": 0.80,
            "generated_at": "2026-09-18T00:20:00Z",
            "stop_loss": 74600.0,
            "take_profit": 78500.0,
            "rationale": "Crypto safe-haven bid and institutional ETF flows. Strong reclaim above $76,000 baseline with momentum indicators pointing towards $78,500 target.",
            "reevaluation_trigger": "Whale wallet distribution spike",
            "invalidation": "74200.0 breakdown",
        },
        {
            "id": 5,
            "symbol": "XTIUSD",
            "decision": "buy",
            "confidence": 0.84,
            "generated_at": "2026-09-18T00:15:00Z",
            "stop_loss": 94.80,
            "take_profit": 99.40,
            "rationale": "Geopolitical supply disruption risk premium escalating. Crude oil inventory drawdown reinforces upside breakout potential.",
            "reevaluation_trigger": "OPEC unexpected quota increase",
            "invalidation": "94.20 support loss",
        },
        {
            "id": 6,
            "symbol": "GBPUSD",
            "decision": "wait",
            "confidence": 0.54,
            "generated_at": "2026-09-18T00:10:00Z",
            "stop_loss": None,
            "take_profit": None,
            "rationale": "Consolidating inside narrow 80-pip channel ahead of UK retail sales data. No high-edge directional setup identified.",
            "reevaluation_trigger": "Post-news breakout above 1.3390 or below 1.3310",
            "invalidation": None,
        },
    ]


@app.get("/api/paper-trading")
@app.get("/api/paper-trading/stats")
@app.get("/api/trading/paper-summary")
async def paper_stats():
    return {
        "total_trades": 1147,
        "market_trades": 1147,
        "wins": 952,
        "losses": 195,
        "win_rate_market_pct": 83.0,
        "win_rate_pct": 83.0,
        "avg_pnl_pct": 1.45,
        "total_pnl_pct": 184.50,
        "avg_win_pct": 2.15,
        "avg_loss_pct": -0.85,
        "avg_rr_achieved": 2.18,
        "expectancy_per_trade_pct": 1.61,
        "expectancy_per_trade_R": 1.63,
        "has_positive_edge": True,
        "edge_alert": False,
        "by_symbol": {
            "XAUUSD": {"trades": 512, "wins": 435, "losses": 77, "pnl_pct": 98.40, "win_rate": 85.0},
            "EURUSD": {"trades": 340, "wins": 275, "losses": 65, "pnl_pct": 42.10, "win_rate": 80.9},
            "BTCUSD": {"trades": 165, "wins": 138, "losses": 27, "pnl_pct": 31.80, "win_rate": 83.6},
            "XTIUSD": {"trades": 130, "wins": 104, "losses": 26, "pnl_pct": 12.20, "win_rate": 80.0},
        },
    }


@app.get("/api/factor-analysis")
@app.get("/api/trading/factor-analysis")
async def factor_analysis():
    return {
        "macro_score": 0.84,
        "technical_score": 0.79,
        "sentiment_score": 0.81,
        "volatility_score": 0.65,
        "composite_confluence": 8.1,
        "factors": {
            "dxy_momentum": {"score": 0.88, "bias": "bullish"},
            "yield_spread": {"score": 0.82, "bias": "bullish"},
            "oil_premium": {"score": 0.85, "bias": "bullish"},
            "cot_positioning": {"score": 0.74, "bias": "neutral"},
            "smc_structure": {"score": 0.86, "bias": "bullish"},
        },
    }


@app.get("/api/edge-metrics")
@app.get("/api/trading/edge-metrics")
async def edge_metrics():
    return {
        "expectancy_r": 1.84,
        "win_rate": 0.6875,
        "loss_rate": 0.3125,
        "average_win_usd": 72.40,
        "average_loss_usd": 32.10,
        "profit_factor": 2.18,
        "edge_ratio": 2.25,
        "sop_benchmark_met": True,
        "total_evaluated_cycles": 847,
    }


@app.get("/api/vix")
async def vix_data(limit: int = 30):
    base_date = datetime(2026, 8, 18)
    points = []
    values = [
        14.2, 14.5, 14.1, 13.9, 14.8, 15.2, 15.6, 16.1, 15.8, 15.2,
        14.9, 15.4, 16.8, 17.5, 18.2, 17.6, 16.9, 16.4, 15.8, 15.3,
        15.5, 15.9, 16.4, 16.9, 17.2, 16.8, 16.2, 15.9, 15.7, 15.82
    ]
    for i, v in enumerate(values[-limit:]):
        d = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")
        points.append({"date": d, "close": v, "open": v - 0.2, "high": v + 0.4, "low": v - 0.3})
    return points


@app.get("/api/brief")
async def get_brief():
    markdown_content = """# Institutional Macroeconomic Intelligence Brief
**Classification**: Stage 1 Macro Foundation Synthesizer  
**Observation Window**: Wednesday, September 16, 2026 — Friday, September 18, 2026  
**Regime Diagnosis**: Hawkish Tightening Cycle & Geopolitical Energy Supply Friction  
**Target Horizon**: Active Trading Session (UTC 00:00 – 22:00)  

---

### 1. Executive Summary & Central Bank Posture
* **Federal Reserve Monetary Policy Action**:
  On September 16, 2026, the Federal Open Market Committee (FOMC) unanimously enacted a **+25 bps interest rate increase**, lifting the Federal Funds Target Rate to **3.75% – 4.00%**. This marks a renewed hawkish vigilance aimed at truncating persistent core inflation.
* **Dot Plot Trajectory**:
  The revised Dot Plot reveals that 16 of 18 members project at least one additional rate increase before year-end 2026, pushing terminal rate projections to **4.10% – 4.25%**.
* **Chairman Press Conference Takeaways**:
  Fed Chair Kevin Warsh explicitly stressed that domestic consumer resilience and recurring energy price spikes demand restrictive financial conditions through Q1 2027. Rate cuts are definitively off the table for the foreseeable horizon.

---

### 2. Commodity Markets & Geopolitical Escalation
* **Crude Oil Structural Supply Squeeze**:
  Crude benchmarks experienced intense upward re-pricing amid geopolitical instability across Middle Eastern transit corridors and the Strait of Hormuz.
  * **WTI Spot (XTIUSD)**: Trading firm at **$97.24/bbl** (+2.40% 24h delta, testing $98.60 intraday ceiling).
  * **Brent Spot (XBRUSD)**: Consolidated above critical triple digits at **$101.05/bbl** (+2.15% 24h delta).
  * **EIA Global Inventory Deficit**: The Energy Information Administration notes commercial petroleum stockpiles stand 6.4% below the 5-year seasonal average.
* **Gold Supercycle & Safe-Haven Resilience (XAUUSD)**:
  Defying conventional real yield headwinds, spot gold maintains exceptional structural demand, trading at **$4,360.50/oz**. Institutional treasury diversification, sovereign central bank accumulation, and geopolitical hedging continue to absorb paper sell orders.

---

### 3. Currency Matrix & Macro Factor Cross-Asset Biases
```
+----------+------------+-----------------------------------------------------------+
| Currency | Regime     | Key Driver & Tactical Confluence                          |
+----------+------------+-----------------------------------------------------------+
| USD      | BULLISH    | +25 bps Fed Hike to 4.00%, Hawkish Dot Plot to 4.10%      |
| EUR      | BEARISH    | Energy import deficit, ECB growth downgrade               |
| JPY      | BEARISH    | Yield divergence vs UST yields, BoJ policy gap            |
| GBP      | NEUTRAL    | Sticky services CPI countered by sluggish manufacturing   |
| CAD      | BULLISH    | Strong oil terms-of-trade export correlation              |
| AUD      | NEUTRAL    | China stimulus baseline balancing commodity exports       |
| CHF      | BEARISH    | Negative carry profile in high global interest environment |
+----------+------------+-----------------------------------------------------------+
```

---

### 4. Tactical Asset Playbook for Stage 2 Multi-Agent Debate
1. **XAUUSD (Gold vs US Dollar)**:
   * **Directive**: Favor BUY on intraday liquidity retests above $4,342.00 support.
   * **Confluence Target**: $4,388.00 / $4,400.00 extension. Invalidation below $4,330.00.
2. **EURUSD**:
   * **Directive**: Favor SELL on rallies towards 1.1495 - 1.1510 supply cluster.
   * **Confluence Target**: 1.1420 liquidity pool.
3. **USDJPY**:
   * **Directive**: Accumulate BUY dips near 155.60 - 155.80, targeting 156.80.
4. **BTCUSD**:
   * **Directive**: Maintain long exposure, holding stop below $74,600 with target $78,500."""

    return {
        "brief": {
            "id": "brief-20260918-01",
            "generated_at": "2026-09-18T00:15:00Z",
            "valid_until": "2026-09-18T08:00:00Z",
            "content_markdown": markdown_content,
            "structured": {
                "macro_regime": "Hawkish Tightening / Energy Crisis",
                "fed_rate": "3.75% - 4.00%",
                "dxy_bias": "bullish",
                "vix_level": 15.82,
                "currency_bias": {
                    "USD": "bullish",
                    "EUR": "bearish",
                    "JPY": "bearish",
                    "GBP": "neutral",
                    "CAD": "bullish",
                    "AUD": "neutral",
                    "CHF": "bearish",
                    "NZD": "neutral",
                },
            },
        }
    }


@app.get("/api/risk")
@app.get("/api/trading/risk")
async def risk_state():
    return {
        "date": "2026-09-18T00:45:00Z",
        "daily_pnl": 438.00,
        "daily_loss": 0.0,
        "current_drawdown": 85.00,
        "drawdown_limit": 300.00,
        "trading_paused": False,
        "reason": None,
        "streak_losses": 0,
        "positions_count": 3,
        "circuit_breaker": "ARMED",
        "margin_utilization_pct": 14.2,
        "portfolio_var_pct": 1.18,
    }


@app.get("/api/gemini-quota")
async def gemini_quota():
    return {"requests_remaining": 845, "limit": 1000, "reset_time": "2026-09-19T00:00:00Z"}


@app.get("/api/decision-distribution")
@app.get("/api/trading/decision-distribution")
async def decision_distribution():
    return {
        "buy": 5,
        "sell": 2,
        "wait": 3,
        "avoid": 1,
        "skip": 1,
        "total": 12,
    }


@app.get("/api/analysis-quality-realtime")
@app.get("/api/trading/analysis-quality")
async def analysis_quality():
    return {
        "total_actionable_analyses": 48,
        "missing_confluence_score_pct": 0.0,
        "missing_priced_in_score_pct": 0.0,
        "avg_confluence_score": 7.85,
        "avg_priced_in_score": 0.65,
        "compliance_rate_pct": 98.4,
        "confluence_score_distribution": {"high": 34, "medium": 12, "low": 2},
        "closed_trades_7d": 64,
        "win_rate_pct": 68.75,
        "alert": False,
    }


@app.get("/api/signals/mt5")
@app.get("/api/trading/signals/mt5")
async def mt5_signals(limit: int = 50):
    return {
        "total": 1147,
        "executed_count": 1147,
        "items": [
            {
                "id": 1,
                "asset_analysis_id": 101,
                "symbol": "XAUUSD",
                "action": "BUY",
                "status": "executed",
                "mt5_ticket": 8921041,
                "created_at": "2026-09-17T22:55:00Z",
                "executed_at": "2026-09-17T22:55:00.042Z",
                "error_message": None,
            },
            {
                "id": 2,
                "asset_analysis_id": 102,
                "symbol": "EURUSD",
                "action": "SELL",
                "status": "executed",
                "mt5_ticket": 8921055,
                "created_at": "2026-09-17T21:30:00Z",
                "executed_at": "2026-09-17T21:30:00.058Z",
                "error_message": None,
            },
            {
                "id": 3,
                "asset_analysis_id": 103,
                "symbol": "BTCUSD",
                "action": "BUY",
                "status": "executed",
                "mt5_ticket": 8921072,
                "created_at": "2026-09-17T20:18:00Z",
                "executed_at": "2026-09-17T20:18:00.065Z",
                "error_message": None,
            },
            {
                "id": 4,
                "asset_analysis_id": 104,
                "symbol": "USDJPY",
                "action": "BUY",
                "status": "executed",
                "mt5_ticket": 8921020,
                "created_at": "2026-09-17T18:40:00Z",
                "executed_at": "2026-09-17T18:40:00.038Z",
                "error_message": None,
            },
            {
                "id": 5,
                "asset_analysis_id": 105,
                "symbol": "XTIUSD",
                "action": "BUY",
                "status": "executed",
                "mt5_ticket": 8920988,
                "created_at": "2026-09-17T14:10:00Z",
                "executed_at": "2026-09-17T14:10:00.052Z",
                "error_message": None,
            },
            {
                "id": 6,
                "asset_analysis_id": 106,
                "symbol": "XAUUSD",
                "action": "BUY",
                "status": "executed",
                "mt5_ticket": 8920942,
                "created_at": "2026-09-17T11:20:00Z",
                "executed_at": "2026-09-17T11:20:00.046Z",
                "error_message": None,
            },
            {
                "id": 7,
                "asset_analysis_id": 107,
                "symbol": "GBPUSD",
                "action": "BUY",
                "status": "executed",
                "mt5_ticket": 8920910,
                "created_at": "2026-09-17T09:15:00Z",
                "executed_at": "2026-09-17T09:15:00.055Z",
                "error_message": None,
            },
            {
                "id": 8,
                "asset_analysis_id": 108,
                "symbol": "EURUSD",
                "action": "SELL",
                "status": "executed",
                "mt5_ticket": 8920880,
                "created_at": "2026-09-17T07:45:00Z",
                "executed_at": "2026-09-17T07:45:00.049Z",
                "error_message": None,
            },
            {
                "id": 9,
                "asset_analysis_id": 109,
                "symbol": "BTCUSD",
                "action": "BUY",
                "status": "executed",
                "mt5_ticket": 8920855,
                "created_at": "2026-09-17T05:30:00Z",
                "executed_at": "2026-09-17T05:30:00.062Z",
                "error_message": None,
            },
            {
                "id": 10,
                "asset_analysis_id": 110,
                "symbol": "XBRUSD",
                "action": "BUY",
                "status": "executed",
                "mt5_ticket": 8920820,
                "created_at": "2026-09-17T03:10:00Z",
                "executed_at": "2026-09-17T03:10:00.044Z",
                "error_message": None,
            },
            {
                "id": 11,
                "asset_analysis_id": 111,
                "symbol": "AUDUSD",
                "action": "SELL",
                "status": "executed",
                "mt5_ticket": 8920790,
                "created_at": "2026-09-17T01:25:00Z",
                "executed_at": "2026-09-17T01:25:00.051Z",
                "error_message": None,
            },
            {
                "id": 12,
                "asset_analysis_id": 112,
                "symbol": "USDJPY",
                "action": "BUY",
                "status": "executed",
                "mt5_ticket": 8920745,
                "created_at": "2026-09-16T23:40:00Z",
                "executed_at": "2026-09-16T23:40:00.040Z",
                "error_message": None,
            },
        ],
    }


@app.get("/api/triggers")
@app.get("/api/trading/triggers")
async def triggers(status: Optional[str] = None, limit: int = 50):
    return {
        "total": 1151,
        "fired_count": 1147,
        "pending_count": 4,
        "items": [
            {
                "id": 1,
                "asset_analysis_id": 101,
                "trigger_type": "PRICE_BREAKOUT_M15",
                "status": "pending",
                "condition": "XAUUSD Breakout above 4375.00 resistance with M15 RSI > 60",
                "created_at": "2026-09-18T00:10:00Z",
                "fired_at": None,
            },
            {
                "id": 2,
                "asset_analysis_id": 102,
                "trigger_type": "SUPPORT_RETEST",
                "status": "pending",
                "condition": "USDJPY Pullback retest of 155.80 support following Tokyo fix",
                "created_at": "2026-09-17T23:45:00Z",
                "fired_at": None,
            },
            {
                "id": 3,
                "asset_analysis_id": 103,
                "trigger_type": "LIQUIDITY_RECLAIM",
                "status": "pending",
                "condition": "BTCUSD Bear trap sweep below 76,200 followed by 5m candle close > 76,450",
                "created_at": "2026-09-17T22:30:00Z",
                "fired_at": None,
            },
            {
                "id": 4,
                "asset_analysis_id": 104,
                "trigger_type": "SUPPLY_BLOCK_RETEST",
                "status": "pending",
                "condition": "EURUSD Retest of 1.1505 supply order block on lower volume",
                "created_at": "2026-09-17T21:00:00Z",
                "fired_at": None,
            },
            {
                "id": 5,
                "asset_analysis_id": 105,
                "trigger_type": "FVG_MITIGATION",
                "status": "fired",
                "condition": "XTIUSD FVG Mitigation zone 96.80 confirmed",
                "created_at": "2026-09-17T14:05:00Z",
                "fired_at": "2026-09-17T14:10:00Z",
            },
        ],
    }


@app.get("/api/debate-outcomes")
@app.get("/api/trading/debate-outcomes")
async def debate_outcomes(limit: int = 20):
    return {
        "total": 1,
        "items": [
            {
                "id": 1,
                "symbol": "XAUUSD",
                "decision": "BUY",
                "confidence": 0.845,
                "confluence_score": 8,
                "risk_multiplier": 1.0,
                "rationale": "Sovereign gold accumulation and crude oil inflation premium structurally overpower yield gap headwinds.",
                "specialist_adjudication": {
                    "judge": "MarketAwareJudge",
                    "edge_score": 2.45,
                    "recommended_rr": 2.28,
                },
                "debate_bull_thesis": "Order block holding at $4,342 with institutional buy imbalance.",
                "debate_bear_dissent": "Real yields elevated post-FOMC hike; risk of $4,330 test.",
                "debate_verdict": "BUY",
                "debate_reason": "Asymmetric upside catalyst alignment across macro and micro.",
                "generated_at": "2026-09-18T00:25:30Z",
                "execution_status": "executed",
            }
        ],
    }


@app.get("/api/observability/graph-state")
async def graph_state(cycle_id: Optional[str] = None):
    return {
        "cycle_id": "cycle-847",
        "status": "completed",
        "started_at": "2026-09-18T00:25:00Z",
        "completed_at": "2026-09-18T00:25:12Z",
        "total_duration_ms": 11840.0,
        "total_tokens": {
            "input": 45200,
            "output": 8420,
            "total": 53620,
            "cost_usd": 0.0535,
        },
        "available_cycles": [
            {"cycle_id": "cycle-847", "label": "Cycle #847 (Active Live)", "status": "completed"},
            {"cycle_id": "cycle-846", "label": "Cycle #846 (Archived)", "status": "completed"},
            {"cycle_id": "cycle-845", "label": "Cycle #845 (Archived)", "status": "completed"},
        ],
        "edges": [
            {"from": "fundamental_brief", "to": "prefetch_data", "label": "Macro Context"},
            {"from": "prefetch_data", "to": "bull_advocate", "label": "OHLCV Candles"},
            {"from": "prefetch_data", "to": "bear_dissent", "label": "OHLCV Candles"},
            {"from": "bull_advocate", "to": "debate_judge", "label": "Bull Thesis"},
            {"from": "bear_dissent", "to": "debate_judge", "label": "Bear Dissent"},
            {"from": "debate_judge", "to": "risk_gate", "label": "BUY Verdict"},
            {"from": "risk_gate", "to": "execution", "label": "Cleared (0.05 Lot)"},
        ],
        "nodes": [
            {
                "id": "fundamental_brief",
                "name": "Fundamental Brief",
                "stage": "stage1",
                "status": "done",
                "duration_ms": 3420.0,
                "tokens": {"input": 12500, "output": 2100, "total": 14600, "cost_usd": 0.0146},
                "input_summary": "Macro calendar, FOMC rate hike 4.00%, WTI $97.24, DXY strength, COT positioning",
                "output_payload": {
                    "macro_regime": "Hawkish Tightening & Energy Inflation",
                    "fomc_target": "3.75% - 4.00%",
                    "gold_supercycle": "active",
                    "dxy_bias": "bullish",
                    "vix": 15.82,
                },
                "started_at": "2026-09-18T00:25:00Z",
                "completed_at": "2026-09-18T00:25:03.42Z",
                "error": None,
            },
            {
                "id": "prefetch_data",
                "name": "Prefetch Data",
                "stage": "prefetch",
                "status": "done",
                "duration_ms": 1180.0,
                "tokens": {"input": 0, "output": 0, "total": 0, "cost_usd": 0.0},
                "input_summary": "Watchlist OHLCV M15/H1: XAUUSD, EURUSD, GBPUSD, USDJPY, BTCUSD, XTIUSD",
                "output_payload": {
                    "symbols_fetched": ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD", "XTIUSD"],
                    "candles_count": 3200,
                    "freshness_ms": 18,
                    "cache_hit": True,
                },
                "started_at": "2026-09-18T00:25:03.42Z",
                "completed_at": "2026-09-18T00:25:04.60Z",
                "error": None,
            },
            {
                "id": "bull_advocate",
                "name": "Bull Advocate",
                "stage": "debate",
                "status": "done",
                "duration_ms": 2850.0,
                "tokens": {"input": 9800, "output": 1850, "total": 11650, "cost_usd": 0.0116},
                "input_summary": "XAUUSD SMC Order Block reclaim at $4,342.00 with liquidity absorption",
                "output_payload": {
                    "thesis": "Bullish market structure continuation. Support floor defended by sovereign accumulation.",
                    "conviction_score": 84.5,
                    "target_price": 4388.00,
                    "upside_catalysts": ["Crude energy rally +2.4%", "Strait of Hormuz supply concerns"],
                },
                "started_at": "2026-09-18T00:25:04.60Z",
                "completed_at": "2026-09-18T00:25:07.45Z",
                "error": None,
            },
            {
                "id": "bear_dissent",
                "name": "Bear Dissent",
                "stage": "debate",
                "status": "done",
                "duration_ms": 2720.0,
                "tokens": {"input": 9600, "output": 1720, "total": 11320, "cost_usd": 0.0113},
                "input_summary": "Overhead sell-side liquidity at $4,375.00, Fed Funds at 4.00% elevating real yields",
                "output_payload": {
                    "counter_thesis": "Elevated real yields increase holding cost of non-yielding assets; risk of pullback to $4,330.",
                    "conviction_score": 46.0,
                    "invalidation_level": 4330.00,
                    "downside_risks": ["Hawkish dot-plot trajectory to 4.10%", "DXY upward thrust"],
                },
                "started_at": "2026-09-18T00:25:04.60Z",
                "completed_at": "2026-09-18T00:25:07.32Z",
                "error": None,
            },
            {
                "id": "debate_judge",
                "name": "Debate Judge",
                "stage": "debate",
                "status": "done",
                "duration_ms": 3150.0,
                "tokens": {"input": 13300, "output": 2750, "total": 16050, "cost_usd": 0.0160},
                "input_summary": "Synthesis of Bull Advocate vs Bear Dissent arguments with micro-playbook matching",
                "output_payload": {
                    "verdict": "BUY",
                    "confidence": 84.5,
                    "confluence_score": 8,
                    "edge_score": 2.45,
                    "reasoning": "Geopolitical risk premium and real physical gold demand structurally overpower yield gap headwinds.",
                    "stop_loss": 4330.00,
                    "take_profit": 4385.00,
                    "risk_reward_ratio": 2.28,
                },
                "started_at": "2026-09-18T00:25:07.45Z",
                "completed_at": "2026-09-18T00:25:10.60Z",
                "error": None,
            },
            {
                "id": "risk_gate",
                "name": "Risk Gate",
                "stage": "risk",
                "status": "done",
                "duration_ms": 420.0,
                "tokens": {"input": 0, "output": 0, "total": 0, "cost_usd": 0.0},
                "input_summary": "Portfolio VaR check, daily drawdown limit (0.85% / 3.0%), correlation matrix, lot sizing",
                "output_payload": {
                    "passed": True,
                    "daily_drawdown_current": 0.85,
                    "max_allowed_daily_dd": 3.0,
                    "adjusted_lot": 0.05,
                    "correlation_check": "passed",
                    "status_message": "Cleared risk gate: Trade sized to 0.75% equity risk ($81.50 SL)",
                },
                "started_at": "2026-09-18T00:25:10.60Z",
                "completed_at": "2026-09-18T00:25:11.02Z",
                "error": None,
            },
            {
                "id": "execution",
                "name": "MT5 Execution",
                "stage": "execution",
                "status": "done",
                "duration_ms": 180.0,
                "tokens": {"input": 0, "output": 0, "total": 0, "cost_usd": 0.0},
                "input_summary": "MetaTrader 5 Python IPC bridge dispatch for Ticket #8921041",
                "output_payload": {
                    "ticket": 8921041,
                    "symbol": "XAUUSD",
                    "action": "BUY",
                    "volume": 0.05,
                    "fill_price": 4345.20,
                    "slippage_points": 2,
                    "execution_latency_ms": 42,
                    "status": "filled",
                },
                "started_at": "2026-09-18T00:25:11.02Z",
                "completed_at": "2026-09-18T00:25:11.20Z",
                "error": None,
            },
        ],
    }


@app.get("/api/v1/tokens/summary")
async def tokens_summary(hours: int = 24):
    return {
        "time_window_hours": hours,
        "total_calls": 284,
        "input_tokens": 1850400,
        "output_tokens": 345100,
        "thinking_tokens": 285000,
        "pure_content_tokens": 60100,
        "thinking_pct_of_output": 82.5,
        "total_tokens": 2480500,
        "cached_tokens": 1969500,
        "cache_creation_tokens": 210000,
        "cache_hit_rate_pct": 79.4,
        "total_cost_usd": 4.18,
        "avg_latency_ms": 1420.5,
        "success_count": 282,
        "fallback_count": 2,
        "rate_limit_count": 0,
        "error_count": 0,
        "context_tracker": {
            "active_cycles": 1,
            "peak_context_tokens": 68400,
            "average_context_tokens": 34200,
        },
    }


@app.get("/api/v1/tokens/roles")
async def tokens_roles(hours: int = 24):
    return {
        "total_roles": 7,
        "items": [
            {"task_role": "stage1_macro", "subsystem": "stage1", "calls": 24, "avg_input": 12500, "avg_output": 2100, "avg_thinking": 1800, "sum_thinking": 43200, "thinking_pct": 85.7, "avg_total": 14600, "sum_total": 520400, "sum_cached": 438000, "sum_cost_usd": 1.15, "avg_latency_ms": 3210.0, "fallback_calls": 0},
            {"task_role": "debate_judge", "subsystem": "debate", "calls": 32, "avg_input": 13300, "avg_output": 2750, "avg_thinking": 2200, "sum_thinking": 70400, "thinking_pct": 80.0, "avg_total": 16050, "sum_total": 485000, "sum_cached": 395000, "sum_cost_usd": 0.98, "avg_latency_ms": 2980.0, "fallback_calls": 1},
            {"task_role": "bull_advocate", "subsystem": "debate", "calls": 48, "avg_input": 9800, "avg_output": 1850, "avg_thinking": 1500, "sum_thinking": 72000, "thinking_pct": 81.0, "avg_total": 11650, "sum_total": 412000, "sum_cached": 321000, "sum_cost_usd": 0.62, "avg_latency_ms": 2150.0, "fallback_calls": 0},
            {"task_role": "bear_dissent", "subsystem": "debate", "calls": 48, "avg_input": 9600, "avg_output": 1720, "avg_thinking": 1400, "sum_thinking": 67200, "thinking_pct": 81.4, "avg_total": 11320, "sum_total": 398000, "sum_cached": 308000, "sum_cost_usd": 0.59, "avg_latency_ms": 2080.0, "fallback_calls": 0},
            {"task_role": "news_watcher", "subsystem": "news", "calls": 96, "avg_input": 3200, "avg_output": 450, "avg_thinking": 300, "sum_thinking": 28800, "thinking_pct": 66.7, "avg_total": 3650, "sum_total": 320000, "sum_cached": 238000, "sum_cost_usd": 0.28, "avg_latency_ms": 840.0, "fallback_calls": 0},
            {"task_role": "risk_evaluator", "subsystem": "risk", "calls": 32, "avg_input": 4500, "avg_output": 620, "avg_thinking": 400, "sum_thinking": 12800, "thinking_pct": 64.5, "avg_total": 5120, "sum_total": 185100, "sum_cached": 142000, "sum_cost_usd": 0.34, "avg_latency_ms": 910.0, "fallback_calls": 1},
            {"task_role": "desk_chat", "subsystem": "console", "calls": 4, "avg_input": 8400, "avg_output": 1600, "avg_thinking": 1200, "sum_thinking": 4800, "thinking_pct": 75.0, "avg_total": 10000, "sum_total": 160000, "sum_cached": 127500, "sum_cost_usd": 0.22, "avg_latency_ms": 1650.0, "fallback_calls": 0},
        ],
    }


@app.get("/api/v1/tokens/subsystems")
async def tokens_subsystems(hours: int = 24):
    return {
        "total_subsystems": 5,
        "items": [
            {"subsystem": "debate", "calls": 128, "sum_input": 980000, "sum_output": 185000, "sum_thinking": 150000, "sum_total": 1295000, "sum_cached": 1024000, "sum_cost_usd": 2.19, "pct_tokens": 52.2, "pct_cost": 52.4},
            {"subsystem": "stage1", "calls": 24, "sum_input": 440000, "sum_output": 80400, "sum_thinking": 68000, "sum_total": 520400, "sum_cached": 438000, "sum_cost_usd": 1.15, "pct_tokens": 21.0, "pct_cost": 27.5},
            {"subsystem": "news", "calls": 96, "sum_input": 275000, "sum_output": 45000, "sum_thinking": 30000, "sum_total": 320000, "sum_cached": 238000, "sum_cost_usd": 0.28, "pct_tokens": 12.9, "pct_cost": 6.7},
            {"subsystem": "risk", "calls": 32, "sum_input": 160000, "sum_output": 25100, "sum_thinking": 18000, "sum_total": 185100, "sum_cached": 142000, "sum_cost_usd": 0.34, "pct_tokens": 7.5, "pct_cost": 8.1},
            {"subsystem": "console", "calls": 4, "sum_input": 135000, "sum_output": 25000, "sum_thinking": 19000, "sum_total": 160000, "sum_cached": 127500, "sum_cost_usd": 0.22, "pct_tokens": 6.4, "pct_cost": 5.3},
        ],
    }


@app.get("/api/v1/tokens/symbols")
async def tokens_symbols(hours: int = 24):
    return {
        "total_symbols": 6,
        "items": [
            {"symbol": "XAUUSD", "calls": 82, "sum_total": 780000, "sum_thinking": 115000, "sum_cached": 620000, "sum_cost_usd": 1.45},
            {"symbol": "EURUSD", "calls": 64, "sum_total": 540000, "sum_thinking": 78000, "sum_cached": 430000, "sum_cost_usd": 0.94},
            {"symbol": "USDJPY", "calls": 48, "sum_total": 420000, "sum_thinking": 56000, "sum_cached": 335000, "sum_cost_usd": 0.72},
            {"symbol": "BTCUSD", "calls": 42, "sum_total": 380000, "sum_thinking": 48000, "sum_cached": 302000, "sum_cost_usd": 0.61},
            {"symbol": "XTIUSD", "calls": 28, "sum_total": 240000, "sum_thinking": 31000, "sum_cached": 191000, "sum_cost_usd": 0.32},
            {"symbol": "GBPUSD", "calls": 20, "sum_total": 120500, "sum_thinking": 15000, "sum_cached": 91500, "sum_cost_usd": 0.14},
        ],
    }


@app.get("/api/v1/tokens/recent")
async def tokens_recent(limit: int = 50):
    logs = [
        {"id": 1, "timestamp": "2026-09-18T00:25:10Z", "provider": "anthropic", "model_name": "claude-3-5-sonnet-20241022", "task_name": "adjudicate_debate", "task_role": "debate_judge", "subsystem": "debate", "symbol": "XAUUSD", "cycle_id": "cycle-847", "input_tokens": 13300, "output_tokens": 2750, "thinking_tokens": 2200, "total_tokens": 16050, "cached_tokens": 11200, "cost_estimate": 0.0160},
        {"id": 2, "timestamp": "2026-09-18T00:25:07Z", "provider": "gemini", "model_name": "gemini-1.5-pro", "task_name": "generate_bull_thesis", "task_role": "bull_advocate", "subsystem": "debate", "symbol": "XAUUSD", "cycle_id": "cycle-847", "input_tokens": 9800, "output_tokens": 1850, "thinking_tokens": 1500, "total_tokens": 11650, "cached_tokens": 8400, "cost_estimate": 0.0116},
        {"id": 3, "timestamp": "2026-09-18T00:25:07Z", "provider": "gemini", "model_name": "gemini-1.5-pro", "task_name": "generate_bear_dissent", "task_role": "bear_dissent", "subsystem": "debate", "symbol": "XAUUSD", "cycle_id": "cycle-847", "input_tokens": 9600, "output_tokens": 1720, "thinking_tokens": 1400, "total_tokens": 11320, "cached_tokens": 8200, "cost_estimate": 0.0113},
        {"id": 4, "timestamp": "2026-09-18T00:25:00Z", "provider": "anthropic", "model_name": "claude-3-5-sonnet-20241022", "task_name": "stage1_macro_brief", "task_role": "stage1_macro", "subsystem": "stage1", "symbol": "ALL", "cycle_id": "cycle-847", "input_tokens": 12500, "output_tokens": 2100, "thinking_tokens": 1800, "total_tokens": 14600, "cached_tokens": 9800, "cost_estimate": 0.0146},
        {"id": 5, "timestamp": "2026-09-18T00:20:00Z", "provider": "gemini", "model_name": "gemini-1.5-flash", "task_name": "news_sentiment_audit", "task_role": "news_watcher", "subsystem": "news", "symbol": "USD", "cycle_id": "news-184", "input_tokens": 4200, "output_tokens": 450, "thinking_tokens": 300, "total_tokens": 4650, "cached_tokens": 3600, "cost_estimate": 0.0018},
    ]
    return {"total": len(logs), "items": logs}


@app.get("/api/config/settings")
async def config_settings():
    from config.settings import load_settings
    settings_path = ROOT_DIR / "trading-agent" / "config" / "settings.yaml"
    raw = settings_path.read_text(encoding="utf-8") if settings_path.exists() else ""
    cfg = load_settings()
    return {"status": "ok", "settings": cfg, "raw_yaml": raw, "file_path": str(settings_path)}


@app.get("/api/config/schema")
async def config_schema():
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "TradingAgentConfig",
        "type": "object",
        "properties": {
            "trading": {"type": "object"},
            "llm": {"type": "object"},
            "database": {"type": "object"},
            "mt5": {"type": "object"},
        },
    }


@app.websocket("/ws/live-feed")
async def ws_live_feed(websocket: WebSocket):
    await websocket.accept()
    try:
        # Send initial live ticks
        for sym, q in MARKET_QUOTES.items():
            await websocket.send_text(json.dumps({
                "type": "tick",
                "symbol": sym,
                "bid": q["bid"],
                "ask": q["ask"],
                "spread": q["spread"],
                "time": time.time(),
            }))
        while True:
            await asyncio.sleep(5)
            await websocket.send_text(json.dumps({"type": "heartbeat", "time": time.time()}))
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/agent-chat")
async def ws_agent_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        await websocket.send_text(json.dumps({"type": "connection_established"}))
        await asyncio.sleep(0.1)
        
        chat_history = [
            {
                "id": "msg-1",
                "role": "assistant",
                "text": "Greetings, Operator. I am Monika, your autonomous quantitative MT5 Trading Agent. Multi-agent debate loops, institutional SMC structure scanners, and deterministic RiskGate invariants are fully synchronized. How may I assist the execution desk today?",
                "timestamp": "2026-09-18T00:08:00Z",
            },
            {
                "id": "msg-2",
                "role": "user",
                "text": "Perform a predictive analysis on whether the Federal Reserve will definitely hike interest rates, and how market expectations are likely to respond to the Fed rate hike given that it is already 90% priced in.",
                "timestamp": "2026-09-18T00:09:15Z",
            },
            {
                "id": "msg-3",
                "role": "assistant",
                "text": (
                    "### Institutional Macro & Cross-Asset Predictive Synthesis\n\n"
                    "**1. Fed Policy Stance & Hike Certainty (3.75% → 4.00%)**\n"
                    "Based on 30-Day Fed Funds futures and Overnight Index Swaps (OIS), a 25 bps hike to **3.75%–4.00%** is **90.4% priced in**. An outright pause would trigger an acute central bank credibility crisis. Underlying economic drivers:\n"
                    "• **Core PCE Persistence**: Core PCE inflation remains stubbornly anchored at **3.1% YoY**, reinforced by shelter costs and escalating shipping/energy transit surcharges.\n"
                    "• **Labor Market Buffer**: Non-Farm Payrolls 3-month rolling average (+174k) and U3 unemployment at **4.1%** give the FOMC leeway to maintain a restrictive posture.\n\n"
                    "**2. Market Response Mechanics: Why the 25 bps Nominal Hike Is Neutral**\n"
                    "Because the 25 bps increase is ~90% discounted, **the rate decision itself will produce zero sustainable alpha**. Asset repricing will be governed entirely by Chair Powell's guidance on the **Terminal Rate Projection** and the **Summary of Economic Projections (SEP)**:\n\n"
                    "• **Scenario A: Hawkish Hike (Terminal Dot Raised to 4.25%-4.50%, 65% Probability)**\n"
                    "  - **US Dollar Index (DXY)**: Bullish breakout through 105.20 resistance toward 105.80 on expanding interest rate differentials.\n"
                    "  - **Treasury Yields**: Bearish flattening; 2Y yield rises toward 4.35%, 10Y benchmarks near 4.15%.\n"
                    "  - **XAUUSD (Gold)**: Brief knee-jerk liquidity dip toward $4,325-$4,335 order block, immediately absorbed by sovereign de-dollarization flows.\n"
                    "  - **EURUSD**: Rejection at 1.1505 supply zone, accelerating downward toward 1.1420 liquidity pool.\n\n"
                    "• **Scenario B: Dovish Hike ('One-and-Done' Terminal Cap at 4.00%, 35% Probability)**\n"
                    "  - Triggers classic *'Sell-the-News'* dollar liquidation (DXY sliding below 104.00), catapulting Gold above $4,400.\n\n"
                    "**3. Desk Action Recommendation**\n"
                    "Maintain trailing stop on active XAUUSD BUY (#8921041) at $4,348.00 (locking +$140 profit); keep EURUSD short hedge open. Order proposal ready for confirmation below:"
                ),
                "timestamp": "2026-09-18T00:11:00Z",
                "toolsUsed": ["MacroeconomicPrefetch", "FedWatchCalculator", "SMCStructureScanner", "TimesFMVolatilityCheck"],
                "pendingAction": {
                    "id": "act-9912",
                    "action_type": "MT5_LIMIT_ORDER",
                    "description": "BUY 0.05 XAUUSD @ 4358.50 (SL: 4342.00, TP: 4392.00) - Confluence Score 8.5/10",
                    "params": {
                        "symbol": "XAUUSD",
                        "volume": 0.05,
                        "action": "BUY",
                        "entry": 4358.50,
                        "stop_loss": 4342.00,
                        "take_profit": 4392.00,
                        "rr_ratio": "1:2.03"
                    }
                }
            }
        ]
        
        await websocket.send_text(json.dumps({"type": "history", "messages": chat_history}))
        
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass


# Static SPA Mount
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(str(FRONTEND_DIST / "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        target = FRONTEND_DIST / full_path
        if target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(FRONTEND_DIST / "index.html"))


def run_server():
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


def capture_screenshot(tab: str, output_name: str, delay_ms: int = 3500):
    url = f"{BASE_URL}/?tab={tab}&theme=light&noboot=1"
    out_file = DOCS_IMG_DIR / output_name
    print(f"[*] Capturing tab '{tab}' (Light Mode) -> {out_file.name} ...")
    
    cmd = [
        str(CHROME_PATH),
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--window-size=1600,1000",
        f"--virtual-time-budget={delay_ms}",
        "--run-all-compositor-stages-before-draw",
        f"--screenshot={str(out_file)}",
        url,
    ]
    
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    if out_file.exists() and out_file.stat().st_size > 15000:
        print(f"    [OK] Captured {out_file.name} ({out_file.stat().st_size // 1024} KB)")
        return True
    else:
        print(f"    [WARN] Initial capture small ({out_file.stat().st_size if out_file.exists() else 0} bytes), retrying without virtual time...")
        cmd_fallback = [
            str(CHROME_PATH),
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--window-size=1600,1000",
            f"--screenshot={str(out_file)}",
            url,
        ]
        time.sleep(1.0)
        subprocess.run(cmd_fallback, capture_output=True, text=True, timeout=25)
        if out_file.exists():
            print(f"    [OK] Captured {out_file.name} ({out_file.stat().st_size // 1024} KB)")
            return True
        print(f"    [FAILED] {out_file.name}")
        return False


async def capture_tui_screenshot():
    print("[*] Generating Terminal UI (TUI) screenshot (Daylight Light Mode) ...")
    from cli.tui import TradingDashboard
    
    app_tui = TradingDashboard(api_url=BASE_URL, theme_name="daylight")
    async with app_tui.run_test(size=(140, 42)) as pilot:
        await pilot.pause(1.2)
        svg_content = app_tui.export_screenshot()
        
    svg_path = DOCS_IMG_DIR / "10_terminal_ui_tui.svg"
    png_path = DOCS_IMG_DIR / "10_terminal_ui_tui.png"
    svg_path.write_text(svg_content, encoding="utf-8")
    
    file_url = f"file:///{str(svg_path).replace('\\', '/')}"
    cmd = [
        str(CHROME_PATH),
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--window-size=1400,900",
        f"--screenshot={str(png_path)}",
        file_url,
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    
    if png_path.exists():
        print(f"    [OK] Captured {png_path.name} ({png_path.stat().st_size // 1024} KB)")
    else:
        print("    [WARN] PNG rendering from SVG failed, SVG preserved.")


def main():
    print(f"=== Monika AI Trading Agent Showcase Generator ===")
    print(f"Target directory: {DOCS_IMG_DIR}")
    print(f"Using Chrome at: {CHROME_PATH}")
    
    # 1. Start ephemeral mock server in background thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    import urllib.request
    print("[*] Waiting for mock server to be healthy...")
    ready = False
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/api/ping", timeout=1) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.5)
            
    if not ready:
        print("[ERROR] Mock server failed to boot in 15 seconds.")
        sys.exit(1)
        
    print("[OK] Server is ready at " + BASE_URL)
    
    # 2. Capture the 9 Web Dashboard Tabs
    tabs_to_capture = [
        ("overview", "01_trading_desk_overview.png", 3500),
        ("signals", "02_trading_desk_signals.png", 3500),
        ("market", "03_trading_desk_market.png", 3500),
        ("graph", "04_market_intelligence_pipeline_dag.png", 4000),
        ("brief", "05_market_intelligence_macro_brief.png", 3500),
        ("risk", "06_ledger_risk_limits.png", 3500),
        ("tokens", "07_ledger_llm_token_audit.png", 3500),
        ("chat", "08_telegraph_desk_console_chat.png", 4000),
        ("config", "09_system_configuration.png", 3500),
    ]
    
    for tab, out_name, delay_ms in tabs_to_capture:
        capture_screenshot(tab, out_name, delay_ms=delay_ms)
        
    # 3. Capture the 10th item: Terminal UI (TUI)
    try:
        asyncio.run(capture_tui_screenshot())
    except Exception as e:
        print(f"[WARN] TUI capture encountered error: {e}")
        
    print("\n=== Showcase Generation Completed ===")
    for img in sorted(DOCS_IMG_DIR.glob("*.png")):
        print(f"- {img.name} ({img.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
