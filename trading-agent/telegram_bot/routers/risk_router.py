"""Legacy compatibility shim for telegram_bot.routers.risk_router."""
import sys as _sys
import monika.interfaces.telegram.routers.risk_router as _canonical

_sys.modules[__name__] = _canonical
