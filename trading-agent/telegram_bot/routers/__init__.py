"""Legacy compatibility shim for telegram_bot.routers."""
import sys as _sys
import monika.interfaces.telegram.routers as _canonical

_sys.modules[__name__] = _canonical
