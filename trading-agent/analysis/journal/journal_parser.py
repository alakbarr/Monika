# ==============================================================================
# File: analysis/journal/journal_parser.py
# Monika Multi-Broker Trade Journal & Statement Ingestion Engine
# ==============================================================================

"""
Multi-broker trade statement parser with resilient encoding and format detection.

Supports:
1. MetaTrader 4 / MetaTrader 5 (Detailed statement HTML & CSV exports)
2. cTrader CSV statement exports
3. Binance & Bybit spot/futures trade history CSV
4. Generic CSV trade journals (date, symbol, side, price, size, pnl)
"""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("TradingAgent.JournalParser")

ENCODING_CANDIDATES = ["utf-8-sig", "utf-8", "utf-16", "gbk", "latin-1"]


@dataclass(frozen=True, slots=True)
class BrokerTrade:
    ticket: str
    symbol: str
    action: str              # 'buy' | 'sell'
    lots: float
    open_time: datetime
    close_time: datetime
    open_price: float
    close_price: float
    sl: float = 0.0
    tp: float = 0.0
    pnl: float = 0.0
    commission: float = 0.0
    swap: float = 0.0
    holding_seconds: float = 0.0
    comment: str = ""


class JournalParser:
    """Parses raw broker export bytes or text into standardized BrokerTrade objects."""

    @classmethod
    def read_text_with_fallback(cls, raw_bytes: bytes) -> str:
        """Decodes raw statement bytes trying multiple encodings."""
        for enc in ENCODING_CANDIDATES:
            try:
                return raw_bytes.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw_bytes.decode("utf-8", errors="replace")

    @classmethod
    def _parse_datetime(cls, val: str) -> Optional[datetime]:
        val = str(val or "").strip()
        if not val:
            return None
        # Replace dot or slash with hyphen
        norm = val.replace(".", "-").replace("/", "-")
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%m-%d-%Y %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
        ):
            try:
                dt = datetime.strptime(norm, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    @classmethod
    def _parse_float(cls, val: Any, default: float = 0.0) -> float:
        if val is None:
            return default
        cleaned = re.sub(r"[^\d.-]", "", str(val).replace(",", "."))
        try:
            return float(cleaned)
        except ValueError:
            return default

    @classmethod
    def parse_csv(cls, text_content: str) -> List[BrokerTrade]:
        """Parses CSV formats (MetaTrader CSV, cTrader, Binance, Generic)."""
        trades: List[BrokerTrade] = []
        lines = [line.strip() for line in text_content.splitlines() if line.strip()]
        if not lines:
            return trades

        # Detect delimiter (comma, semicolon, tab)
        sample = "\n".join(lines[:10])
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
            delimiter = dialect.delimiter
        except Exception:
            delimiter = "," if "," in lines[0] else "\t"

        reader = csv.reader(lines, delimiter=delimiter)
        header_row = None
        header_idx: Dict[str, int] = {}

        for row in reader:
            if not row or not any(row):
                continue

            low_row = [str(c).strip().lower() for c in row]

            # Detect header row
            if any(k in low_row for k in ("symbol", "item", "ticker", "instrument")) and any(
                k in low_row for k in ("pnl", "profit", "gain", "net profit", "close price", "type", "action")
            ):
                header_row = low_row
                header_idx = {col: i for i, col in enumerate(header_row)}
                continue

            if not header_row:
                continue

            # Column lookup helpers
            def get_val(possible_keys: Tuple[str, ...], default: str = "") -> str:
                for k in possible_keys:
                    for col_name, idx in header_idx.items():
                        if k == col_name or k in col_name:
                            if idx < len(row):
                                return row[idx].strip()
                return default

            symbol = get_val(("symbol", "item", "ticker", "instrument")).upper().replace("/", "")
            if not symbol or symbol in ("BALANCE", "CREDIT", "DEPOSIT", "WITHDRAWAL"):
                continue

            action_raw = get_val(("action", "type", "direction", "side")).lower()
            action = "buy" if "buy" in action_raw or "long" in action_raw else ("sell" if "sell" in action_raw or "short" in action_raw else "")
            if not action:
                continue

            ticket = get_val(("ticket", "order", "id", "deal", "trade id"), str(len(trades) + 1))
            lots = cls._parse_float(get_val(("lots", "volume", "size", "quantity", "amount")), 0.01)
            open_price = cls._parse_float(get_val(("open price", "price", "entry price", "open_price")), 0.0)
            close_price = cls._parse_float(get_val(("close price", "exit price", "close_price")), open_price)
            pnl = cls._parse_float(get_val(("profit", "pnl", "net profit", "realized pnl")), 0.0)
            commission = cls._parse_float(get_val(("commission", "fee", "comm")), 0.0)
            swap = cls._parse_float(get_val(("swap", "financing", "interest")), 0.0)
            sl = cls._parse_float(get_val(("s/l", "sl", "stop loss")), 0.0)
            tp = cls._parse_float(get_val(("t/p", "tp", "take profit")), 0.0)

            open_time = cls._parse_datetime(get_val(("open time", "open_time", "time", "date", "created_at")))
            close_time = cls._parse_datetime(get_val(("close time", "close_time", "exit time", "closed_at"))) or open_time

            if not open_time:
                open_time = datetime.now(timezone.utc)
            if not close_time:
                close_time = open_time

            holding_sec = max(0.0, (close_time - open_time).total_seconds())

            trades.append(
                BrokerTrade(
                    ticket=ticket,
                    symbol=symbol,
                    action=action,
                    lots=lots,
                    open_time=open_time,
                    close_time=close_time,
                    open_price=open_price,
                    close_price=close_price,
                    sl=sl,
                    tp=tp,
                    pnl=pnl,
                    commission=commission,
                    swap=swap,
                    holding_seconds=holding_sec,
                    comment=get_val(("comment", "notes", "memo"), ""),
                )
            )

        return trades

    @classmethod
    def parse_html_report(cls, html_content: str) -> List[BrokerTrade]:
        """Parses MetaTrader 4/5 HTML report tables."""
        from bs4 import BeautifulSoup

        trades: List[BrokerTrade] = []
        soup = BeautifulSoup(html_content, "html.parser")

        for row in soup.find_all("tr"):
            cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 10:
                continue

            # Standard MT4/MT5 closed trades row:
            # Ticket, Open Time, Type, Size, Item, Price, S/L, T/P, Close Time, Price, Commission, Taxes, Swap, Profit
            ticket = cells[0]
            if not ticket.isdigit():
                continue

            action_raw = cells[2].lower()
            if action_raw not in ("buy", "sell"):
                continue

            open_time = cls._parse_datetime(cells[1])
            lots = cls._parse_float(cells[3], 0.01)
            symbol = cells[4].upper().replace("/", "")
            open_price = cls._parse_float(cells[5], 0.0)
            sl = cls._parse_float(cells[6], 0.0)
            tp = cls._parse_float(cells[7], 0.0)
            close_time = cls._parse_datetime(cells[8])
            close_price = cls._parse_float(cells[9], open_price)

            pnl = cls._parse_float(cells[-1], 0.0)
            swap = cls._parse_float(cells[-2], 0.0) if len(cells) >= 12 else 0.0
            commission = cls._parse_float(cells[-3], 0.0) if len(cells) >= 13 else 0.0

            if not open_time:
                open_time = datetime.now(timezone.utc)
            if not close_time:
                close_time = open_time

            holding_sec = max(0.0, (close_time - open_time).total_seconds())

            trades.append(
                BrokerTrade(
                    ticket=ticket,
                    symbol=symbol,
                    action=action_raw,
                    lots=lots,
                    open_time=open_time,
                    close_time=close_time,
                    open_price=open_price,
                    close_price=close_price,
                    sl=sl,
                    tp=tp,
                    pnl=pnl,
                    commission=commission,
                    swap=swap,
                    holding_seconds=holding_sec,
                )
            )

        return trades

    @classmethod
    def parse_statement(cls, file_content: Union[str, bytes]) -> List[BrokerTrade]:
        """Auto-detects format (HTML vs CSV) and decodes statements."""
        if isinstance(file_content, bytes):
            text = cls.read_text_with_fallback(file_content)
        else:
            text = file_content

        if "<html" in text.lower() or "<table" in text.lower():
            trades = cls.parse_html_report(text)
            if trades:
                return trades
        return cls.parse_csv(text)
