"""
Filesystem storage adapter for empirical trading playbooks.

Loads markdown playbook specifications and quantitative reserve catalogs
from the repository's skills storage directory. Decoupled from pure domain logic.
"""

from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from monika.domain.market.playbook_screener import PlaybookRegistry, PlaybookSpec

logger = logging.getLogger("TradingAgent.Storage.PlaybookCatalogRepository")


class PlaybookCatalogRepository:
    """Filesystem repository for empirical trading playbooks and reserve catalogs."""

    def __init__(self, playbooks_dir: Optional[Path] = None) -> None:
        self._playbooks_dir: Optional[Path] = playbooks_dir
        self._cached_specs: Dict[str, List[PlaybookSpec]] = {}

    def get_playbooks_dir(self) -> Path:
        """Resolve the playbooks directory path."""
        if self._playbooks_dir is not None and self._playbooks_dir.exists():
            return self._playbooks_dir

        base = Path(__file__).resolve().parents[4] / "skills" / "trading" / "playbooks"
        if base.exists():
            self._playbooks_dir = base
            return base

        fallback = Path("skills/trading/playbooks").resolve()
        if fallback.exists():
            self._playbooks_dir = fallback
            return fallback

        return base

    def set_playbooks_dir(self, custom_dir: Path) -> None:
        """Explicitly override directory for testing or configuration."""
        self._playbooks_dir = custom_dir
        self._cached_specs.clear()

    def load_playbooks_for_symbol(self, symbol: str) -> List[PlaybookSpec]:
        """Load and cache all playbook specifications for a given symbol."""
        sym_clean = symbol.strip().upper()
        if sym_clean in self._cached_specs:
            return self._cached_specs[sym_clean]

        pb_dir = self.get_playbooks_dir()
        if not pb_dir.exists():
            logger.warning(f"Playbooks directory not found at {pb_dir}")
            return []

        specs: List[PlaybookSpec] = []
        prefix = sym_clean.lower() + "_"

        for f in pb_dir.glob("*.md"):
            fname = f.name.lower()
            if not fname.startswith(prefix):
                continue
            try:
                spec = self.parse_playbook_file(f, sym_clean)
                if spec is not None:
                    specs.append(spec)
            except Exception as e:
                logger.debug(f"Failed parsing playbook {f.name}: {e}")

        # Sort by Profit Factor descending to prioritize highest-edge playbooks
        specs.sort(key=lambda s: s.profit_factor, reverse=True)
        self._cached_specs[sym_clean] = specs
        return specs

    def load_reserve_playbooks(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load quantitative reserve playbooks from reserve_catalog.json."""
        pb_dir = self.get_playbooks_dir()
        catalog_path = pb_dir / "reserve_catalog.json"
        if not catalog_path.exists():
            return []
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                data: Dict[str, Any] = json.load(f)
            if symbol:
                sym_clean = symbol.strip().upper()
                res = data.get(sym_clean, [])
                return res if isinstance(res, list) else []
            all_reserves: List[Dict[str, Any]] = []
            for plist in data.values():
                if isinstance(plist, list):
                    all_reserves.extend(plist)
            return all_reserves
        except Exception as e:
            logger.debug(f"Failed loading reserve catalog: {e}")
            return []

    def parse_playbook_file(self, path: Path, expected_symbol: str) -> Optional[PlaybookSpec]:
        """Parse frontmatter and quantitative directives from a markdown playbook file."""
        text = path.read_text(encoding="utf-8")
        return self.parse_playbook_text(text, expected_symbol, path=path)

    def parse_playbook_text(
        self,
        text: str,
        expected_symbol: str,
        path: Optional[Path] = None,
    ) -> Optional[PlaybookSpec]:
        """Parse frontmatter and quantitative directives from markdown text."""
        if not text.startswith("---"):
            return None

        parts = text.split("---", 2)
        if len(parts) < 3:
            return None

        frontmatter_raw = parts[1]
        body = parts[2]

        fm: Dict[str, Any] = {}
        for line in frontmatter_raw.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip().strip("'").strip('"')
            fm[k] = v

        name = fm.get("name", path.stem if path else "unnamed_playbook")
        symbol = fm.get("symbol", expected_symbol).upper()
        if symbol != expected_symbol:
            return None

        def _safe_float(val: Any, default: float) -> float:
            try:
                f_val = float(val)
                return f_val if not math.isnan(f_val) and not math.isinf(f_val) else default
            except ValueError, TypeError:
                return default

        def _safe_int(val: Any, default: int) -> int:
            try:
                return int(val)
            except ValueError, TypeError:
                return default

        pf = _safe_float(fm.get("profit_factor"), 1.3)
        wr = _safe_float(fm.get("win_rate"), 0.5)
        sr = _safe_float(fm.get("sharpe_ratio"), 2.0)
        max_dd = _safe_float(fm.get("max_drawdown_pct"), 8.0)
        min_rr = _safe_float(fm.get("min_rr"), 1.5)
        raw_regime = str(fm.get("regime", "trending")).lower().strip()
        if raw_regime in ("trend", "trending"):
            regime = "trending"
        elif raw_regime in ("range", "ranging", "mean_reverting", "mean_reversion"):
            regime = "mean_reverting"
        elif raw_regime in ("breakout", "momentum"):
            regime = "breakout"
        elif raw_regime in ("volatile", "volatility"):
            regime = "volatile"
        else:
            regime = raw_regime
        timeframe = fm.get("timeframe", "H1")
        description = fm.get("description", "")
        status = fm.get("status", "active")

        # Extract calibrated ATR multipliers from body
        sl_mult = 1.5
        tp_mult = 3.0
        max_hold = 24

        m_sl = re.search(r"Stop-Loss\s*=\s*([\d\.]+)x\s*ATR", body, re.IGNORECASE)
        if m_sl:
            sl_mult = _safe_float(m_sl.group(1), 1.5)
        else:
            m_sl2 = re.search(r"set at ([\d\.]+)x.*?ATR", body, re.IGNORECASE)
            if m_sl2:
                sl_mult = _safe_float(m_sl2.group(1), 1.5)

        m_tp = re.search(r"Take-Profit\s*=\s*([\d\.]+)x\s*ATR", body, re.IGNORECASE)
        if m_tp:
            tp_mult = _safe_float(m_tp.group(1), max(2.5, min_rr * sl_mult))
        else:
            m_tp2 = re.search(r"placed at ([\d\.]+)x.*?ATR", body, re.IGNORECASE)
            if m_tp2:
                tp_mult = _safe_float(m_tp2.group(1), max(2.5, min_rr * sl_mult))

        m_hold = re.search(r"Max Holding\s*=\s*(\d+)\s*bars", body, re.IGNORECASE)
        if m_hold:
            max_hold = _safe_int(m_hold.group(1), 24)
        else:
            m_hold2 = re.search(r"within (\d+) bars", body, re.IGNORECASE)
            if m_hold2:
                max_hold = _safe_int(m_hold2.group(1), 24)

        return PlaybookSpec(
            name=name,
            symbol=symbol,
            regime=regime,
            timeframe=timeframe,
            min_rr=min_rr,
            profit_factor=pf,
            win_rate=wr,
            sharpe_ratio=sr,
            max_drawdown_pct=max_dd,
            sl_atr_mult=sl_mult,
            tp_atr_mult=tp_mult,
            max_hold_bars=max_hold,
            description=description,
            status=status,
            file_path=path,
        )


# Register default repository factory into domain registry upon module import
PlaybookRegistry.register_default_repository_factory(lambda: PlaybookCatalogRepository())
