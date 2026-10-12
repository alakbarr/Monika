"""
File: telegram_bot/fuzzy_router.py
Description-aware fuzzy slash command router for Monika Telegram Bot.
Matches trader commands using exact tokens, typographical distance, and semantic description search.
"""

import difflib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class SlashCommandDef:
    command: str
    aliases: List[str]
    description: str
    admin_only: bool = False
    usage: str = ""


# Standard trading command registry
TRADING_COMMAND_REGISTRY: Dict[str, SlashCommandDef] = {
    "status": SlashCommandDef(
        command="status",
        aliases=["s", "kondisi", "keadaan"],
        description="Menampilkan status sistem, flag trading, dan ringkasan portofolio",
        usage="/status"
    ),
    "positions": SlashCommandDef(
        command="positions",
        aliases=["pos", "posisi", "orders", "trades"],
        description="Melihat seluruh posisi aktif (real dan paper)",
        usage="/positions"
    ),
    "risk": SlashCommandDef(
        command="risk",
        aliases=["risiko", "drawdown", "dd"],
        description="Menampilkan metrik risiko akun, margin, dan batas drawdown",
        usage="/risk"
    ),
    "regime": SlashCommandDef(
        command="regime",
        aliases=["rezim", "market_regime", "volatilitas"],
        description="Melihat deteksi regime pasar makro dan volatilitas terkini",
        usage="/regime"
    ),
    "override": SlashCommandDef(
        command="override",
        aliases=["setrisk", "adjust"],
        description="Mengubah parameter risiko dinamis (misal: /override max_risk 1.5)",
        admin_only=True,
        usage="/override <param> <value>"
    ),
    "audit": SlashCommandDef(
        command="audit",
        aliases=["trace", "investigasi"],
        description="Memeriksa jejak audit penalaran trade atau posisi berdasarkan tiket",
        usage="/audit <ticket>"
    ),
    "close": SlashCommandDef(
        command="close",
        aliases=["tutup", "exit"],
        description="Menutup posisi tertentu berdasarkan nomor tiket",
        admin_only=True,
        usage="/close <ticket>"
    ),
    "closeall": SlashCommandDef(
        command="closeall",
        aliases=["tutupsemua", "liquidate"],
        description="Menutup seluruh posisi aktif dengan konfirmasi cepat",
        admin_only=True,
        usage="/closeall"
    ),
    "pause": SlashCommandDef(
        command="pause",
        aliases=["jeda", "stop_trading"],
        description="Menjeda pembukaan posisi trading baru",
        admin_only=True,
        usage="/pause [alasan]"
    ),
    "resume": SlashCommandDef(
        command="resume",
        aliases=["lanjut", "start_trading"],
        description="Melanjutkan kembali operasional trading",
        admin_only=True,
        usage="/resume"
    ),
    "kill": SlashCommandDef(
        command="kill",
        aliases=["darurat", "killswitch"],
        description="Memicu kill switch darurat dan melikuidasi seluruh eksposur",
        admin_only=True,
        usage="/kill"
    ),
    "brief": SlashCommandDef(
        command="brief",
        aliases=["fundamental", "makro"],
        description="Menampilkan ringkasan intelijen fundamental dan sentimen pasar terkini",
        usage="/brief"
    ),
    "help": SlashCommandDef(
        command="help",
        aliases=["bantuan", "menu"],
        description="Menampilkan daftar perintah dan panduan penggunaan",
        usage="/help"
    ),
}


class FuzzyCommandRouter:
    """Multi-tier command resolver supporting exact, typo, and description matching."""

    def __init__(self, registry: Optional[Dict[str, SlashCommandDef]] = None):
        self.registry = registry or TRADING_COMMAND_REGISTRY
        self._alias_map: Dict[str, str] = {}
        for cmd_name, defn in self.registry.items():
            self._alias_map[cmd_name.lower()] = cmd_name
            for alias in defn.aliases:
                self._alias_map[alias.lower()] = cmd_name

    def resolve(self, raw_input: str) -> Tuple[Optional[SlashCommandDef], List[str]]:
        """Resolves input string to a command definition or suggests alternatives.
        
        Returns:
            Tuple of (Matched SlashCommandDef or None, List of suggested command strings)
        """
        token = raw_input.strip().lstrip("/").lower()
        if not token:
            return None, []

        # Tier 0: Exact command or alias match
        if token in self._alias_map:
            canonical = self._alias_map[token]
            return self.registry[canonical], []

        # Tier 1: Typo distance match (difflib)
        all_candidates = list(self._alias_map.keys())
        close_matches = difflib.get_close_matches(token, all_candidates, n=3, cutoff=0.6)
        if close_matches:
            canonical_suggestions = list(dict.fromkeys(
                self._alias_map[m] for m in close_matches
            ))
            # If top match is extremely close (distance <= 1 or cutoff >= 0.8), accept match
            top_ratio = difflib.SequenceMatcher(None, token, close_matches[0]).ratio()
            if top_ratio >= 0.8:
                canonical = self._alias_map[close_matches[0]]
                return self.registry[canonical], []
            return None, [f"/{c}" for c in canonical_suggestions]

        # Tier 2: Description keyword search
        desc_matches = []
        for cmd_name, defn in self.registry.items():
            if token in defn.description.lower():
                desc_matches.append(cmd_name)

        if desc_matches:
            return None, [f"/{c}" for c in desc_matches[:3]]

        return None, []
