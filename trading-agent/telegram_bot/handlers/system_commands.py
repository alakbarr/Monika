"""
System, Analytics, and Governance Commands Group for Telegram Bot.
Defines descriptors, permissions, and handler dispatch mapping for system diagnostics and administration.
"""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class SystemCommandDescriptor:
    name: str
    admin_only: bool
    description: str
    usage: str


SYSTEM_COMMAND_DESCRIPTORS: Dict[str, SystemCommandDescriptor] = {
    "start": SystemCommandDescriptor("start", False, "Inisialisasi bot dan panduan awal", "/start"),
    "help": SystemCommandDescriptor("help", False, "Daftar panduan seluruh perintah bot", "/help"),
    "stats": SystemCommandDescriptor("stats", False, "Statistik performa trading dan metrik akurasi", "/stats"),
    "cost": SystemCommandDescriptor("cost", False, "Rincian biaya API token LLM", "/cost"),
    "credits": SystemCommandDescriptor("credits", False, "Sisa kuota dan billing provider LLM", "/credits"),
    "edge": SystemCommandDescriptor("edge", False, "Evaluasi edge kuantitatif dan expectancy R", "/edge"),
    "calibration": SystemCommandDescriptor("calibration", False, "Kalibrasi probabilitas dan Brier score", "/calibration"),
    "tokens": SystemCommandDescriptor("tokens", False, "Penggunaan token per provider dan model", "/tokens"),
    "report": SystemCommandDescriptor("report", False, "Laporan mingguan ringkas performa agent", "/report"),
    "tearsheet": SystemCommandDescriptor("tearsheet", False, "Quant tearsheet institusional: Sharpe, Sortino, Calmar", "/tearsheet"),
    "history": SystemCommandDescriptor("history", False, "Riwayat 10 transaksi dan aktivitas terakhir", "/history"),
    "risk": SystemCommandDescriptor("risk", False, "Ringkasan metrik risiko dan drawdown", "/risk"),
    "risk_deep": SystemCommandDescriptor("risk_deep", False, "Audit risiko mendalam: VaR, CVaR, dan margin", "/risk_deep"),
    "approvals": SystemCommandDescriptor("approvals", True, "Daftar proposal trade yang memerlukan approval", "/approvals"),
    "backtest": SystemCommandDescriptor("backtest", True, "Jalankan simulasi backtest historis", "/backtest [simbol] [hari]"),
    "pair": SystemCommandDescriptor("pair", False, "Otentikasi dan pairing akun Telegram dengan bot", "/pair [kode]"),
}
