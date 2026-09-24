"""
Deterministic Voice Safety Gate for Telegram Trading Commands.
Extracts structured trade parameters (Action, Symbol, Lots, SL, TP) from transcribed voice text.
Enforces that voice commands NEVER execute immediately; they MUST produce an interactive
Approval Card requiring explicit operator confirmation before MT5 dispatch.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger("TradingAgent.VoiceSafetyGate")

_SYMBOL_ALIASES = {
    "gold": "XAUUSD",
    "emas": "XAUUSD",
    "silver": "XAGUSD",
    "perak": "XAGUSD",
    "bitcoin": "BTCUSD",
    "btc": "BTCUSD",
    "euro": "EURUSD",
    "fiber": "EURUSD",
    "guppy": "GBPJPY",
    "cable": "GBPUSD",
    "pound": "GBPUSD",
    "yen": "USDJPY",
    "usdjpy": "USDJPY",
    "gbpusd": "GBPUSD",
    "eurusd": "EURUSD",
    "xauusd": "XAUUSD",
    "btcusd": "BTCUSD",
    "oil": "XBRUSD",
    "brent": "XBRUSD",
    "crude": "XTIUSD",
}


@dataclass
class VoiceTradeProposal:
    is_trade_command: bool
    action: Optional[str] = None  # "BUY", "SELL", "CLOSE"
    symbol: Optional[str] = None
    lots: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    raw_transcript: str = ""
    error: Optional[str] = None


class VoiceSafetyGate:
    """Safely parses voice transcripts and converts trade requests into interactive approval cards."""

    @staticmethod
    def extract_trade_intent(transcript: str) -> VoiceTradeProposal:
        text = transcript.lower().strip()

        # Check action
        action = None
        if re.search(r"\b(buy|beli|long)\b", text):
            action = "BUY"
        elif re.search(r"\b(sell|jual|short)\b", text):
            action = "SELL"
        elif re.search(r"\b(close|tutup|liquidate)\b", text):
            action = "CLOSE"

        if not action:
            return VoiceTradeProposal(is_trade_command=False, raw_transcript=transcript)

        # Check symbol
        symbol = None
        for alias, canon in _SYMBOL_ALIASES.items():
            if re.search(rf"\b{alias}\b", text):
                symbol = canon
                break

        # Fallback check for uppercase 6-char currency pair
        if not symbol:
            sym_match = re.search(r"\b([a-z]{6})\b", text)
            if sym_match:
                candidate = sym_match.group(1).upper()
                if candidate in ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF"):
                    symbol = candidate

        # Check lots / volume (requires explicit 'lot' or 'volume' keyword to avoid capturing price levels)
        lots = None
        lot_match = re.search(r"(?:volume\s*)?(\d+(?:[.,]\d+)?)\s*(?:lot|lots|volume)\b|(?:volume\s+)(\d+(?:[.,]\d+)?)", text)
        if lot_match:
            try:
                val_str = lot_match.group(1) or lot_match.group(2)
                if val_str:
                    parsed = float(val_str.replace(",", "."))
                    if 0.01 <= parsed <= 100.0:
                        lots = parsed
            except ValueError:
                pass

        # Check SL and TP if mentioned
        sl = None
        tp = None
        sl_match = re.search(r"(?:sl|stop loss|cut loss)\s*(?:di|at|pada)?\s*(\d+(?:[.,]\d+)?)", text)
        if sl_match:
            try:
                sl = float(sl_match.group(1).replace(",", "."))
            except ValueError:
                pass

        tp_match = re.search(r"(?:tp|take profit|target)\s*(?:di|at|pada)?\s*(\d+(?:[.,]\d+)?)", text)
        if tp_match:
            try:
                tp = float(tp_match.group(1).replace(",", "."))
            except ValueError:
                pass

        if not symbol:
            return VoiceTradeProposal(
                is_trade_command=True,
                action=action,
                raw_transcript=transcript,
                error="Simbol aset tidak terdeteksi dari perintah suara."
            )

        if not lots and action != "CLOSE":
            lots = 0.01  # Default minimum lot size safe fallback

        return VoiceTradeProposal(
            is_trade_command=True,
            action=action,
            symbol=symbol,
            lots=lots,
            stop_loss=sl,
            take_profit=tp,
            raw_transcript=transcript,
        )
