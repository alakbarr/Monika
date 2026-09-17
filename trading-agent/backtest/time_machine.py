"""
TimeMachine: Provides point-in-time data access untuk Full Mode.

Implementasi detail:
1. Patch _utcnow() di database/models.py
2. Patch datetime.now(timezone.utc) di semua modul analisis
3. Tool executor query otomatis difilter:
   - get_news_items: WHERE scraped_at <= virtual_time
   - get_price_history: WHERE timestamp <= virtual_time
   - get_economic_calendar: WHERE event_date <= virtual_time
   - get_cot_report: WHERE report_date <= virtual_time
   - get_treasury_yields: WHERE date <= virtual_time
   - get_vix: WHERE date <= virtual_time

Catatan: Tool yang mengambil data external (API call ke luar) di-mock/skip.
Hanya data yang sudah ada di DB yang digunakan.
"""

import contextvars
from datetime import datetime, timezone

# Context var untuk virtual time (thread-safe)
_virtual_time: contextvars.ContextVar[datetime | None] = contextvars.ContextVar(
    'backtest_virtual_time', default=None
)

def get_virtual_now() -> datetime:
    """Mengembalikan virtual_time jika dalam backtest, atau UTC now jika live."""
    vt = _virtual_time.get()
    return vt if vt is not None else datetime.now(timezone.utc)

def is_backtest_mode() -> bool:
    """Apakah sedang dalam backtest mode."""
    return _virtual_time.get() is not None

class TimeMachine:
    """Context manager untuk backtest mode."""
    def __init__(self, virtual_time: datetime):
        self.virtual_time = virtual_time
        self._token: contextvars.Token[datetime | None] | None = None

    async def __aenter__(self):
        self._token = _virtual_time.set(self.virtual_time)
        from utils.clock import set_simulated_now
        set_simulated_now(self.virtual_time)
        return self

    async def __aexit__(self, *args):
        if self._token is not None:
            _virtual_time.reset(self._token)
        from utils.clock import set_simulated_now
        set_simulated_now(None)
