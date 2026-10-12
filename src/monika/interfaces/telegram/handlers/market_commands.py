"""
Market Intelligence & Quantitative Commands Group for Telegram Bot.
Defines descriptors, permissions, and handler dispatch mapping for market data and quant tools.
"""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class MarketCommandDescriptor:
    name: str
    admin_only: bool
    description: str
    usage: str


MARKET_COMMAND_DESCRIPTORS: Dict[str, MarketCommandDescriptor] = {
    "status": MarketCommandDescriptor("status", False, "Status portofolio, agent state, dan risk invariants", "/status"),
    "positions": MarketCommandDescriptor("positions", False, "Daftar posisi aktif di MT5 dan unrealized PnL", "/positions"),
    "brief": MarketCommandDescriptor("brief", False, "Fundamental brief makroekonomi terkini", "/brief"),
    "analysis": MarketCommandDescriptor("analysis", False, "Analisis teknikal dan fundamental mendalam per simbol", "/analysis <simbol>"),
    "pipeline": MarketCommandDescriptor("pipeline", False, "Status pipeline siklus LangGraph", "/pipeline"),
    "vix": MarketCommandDescriptor("vix", False, "Volatilitas pasar dan level VIX terkini", "/vix"),
    "fedwatch": MarketCommandDescriptor("fedwatch", False, "Probabilitas suku bunga FedWatch CME", "/fedwatch"),
    "yields": MarketCommandDescriptor("yields", False, "Kurva yield US Treasury dan spread 10Y-2Y", "/yields"),
    "macro_weekly": MarketCommandDescriptor("macro_weekly", False, "Outlook makroekonomi mingguan terperinci", "/macro_weekly"),
    "weekly_macro": MarketCommandDescriptor("weekly_macro", False, "Alias untuk outlook makro mingguan", "/weekly_macro"),
    "fear_greed": MarketCommandDescriptor("fear_greed", False, "Indeks Fear & Greed pasar global", "/fear_greed"),
    "cot": MarketCommandDescriptor("cot", False, "Laporan CFTC Commitments of Traders terkini", "/cot <simbol>"),
    "calendar": MarketCommandDescriptor("calendar", False, "Kalender rilis data ekonomi high-impact", "/calendar"),
    "smc": MarketCommandDescriptor("smc", False, "Zona Smart Money Concepts: Order Blocks dan FVG", "/smc <simbol>"),
    "factors": MarketCommandDescriptor("factors", False, "Faktor konfluensi dan scoring multi-timeframe", "/factors <simbol>"),
    "alpha": MarketCommandDescriptor("alpha", False, "Sinyal Alpha Zoo formula kuantitatif", "/alpha <simbol>"),
    "chart": MarketCommandDescriptor("chart", False, "Generate chart dan visualisasi harga", "/chart <simbol>"),
}
