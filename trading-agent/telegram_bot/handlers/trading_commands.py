"""
Trading Operations Command Group for Telegram Bot.
Defines descriptors, permissions, and handler dispatch mapping for execution and risk controls.
"""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class CommandDescriptor:
    name: str
    admin_only: bool
    description: str
    usage: str


TRADING_COMMAND_DESCRIPTORS: Dict[str, CommandDescriptor] = {
    "pause": CommandDescriptor("pause", True, "Jeda seluruh eksekusi trading otomatis", "/pause [durasi] [alasan]"),
    "resume": CommandDescriptor("resume", True, "Lanjutkan eksekusi trading setelah dijeda", "/resume"),
    "suspend": CommandDescriptor("suspend", True, "Tangguhkan trading pada simbol tertentu", "/suspend <simbol> [alasan]"),
    "unsuspend": CommandDescriptor("unsuspend", True, "Cabut penangguhan trading pada simbol", "/unsuspend <simbol>"),
    "kill": CommandDescriptor("kill", True, "Emergency liquidation: tutup semua posisi dan jeda sistem", "/kill"),
    "emergency": CommandDescriptor("emergency", True, "Alias untuk kill switch darurat", "/emergency"),
    "close": CommandDescriptor("close", True, "Tutup posisi trading tertentu berdasarkan tiket", "/close <ticket>"),
    "closeall": CommandDescriptor("closeall", True, "Tutup semua posisi terbuka dengan konfirmasi", "/closeall"),
    "override": CommandDescriptor("override", True, "Override status intervensi manual", "/override <alasan>"),
    "run": CommandDescriptor("run", True, "Jalankan siklus analisis dan trading manual secara paksa", "/run"),
    "orders": CommandDescriptor("orders", False, "Daftar order aktif dan pending", "/orders"),
    "trailing": CommandDescriptor("trailing", False, "Status dan pengaturan trailing stop", "/trailing [simbol]"),
    "reconcile": CommandDescriptor("reconcile", True, "Rekonsiliasi posisi antara DB dan broker MT5", "/reconcile"),
}
