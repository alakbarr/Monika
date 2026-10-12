"""Legacy compatibility shim for telegram_bot.routers.trading_router."""
import sys as _sys
import monika.interfaces.telegram.routers.trading_router as _canonical

_sys.modules[__name__] = _canonical
