"""Legacy compatibility shim for telegram_bot.routers.market_router."""
import sys as _sys
import monika.interfaces.telegram.routers.market_router as _canonical

_sys.modules[__name__] = _canonical
