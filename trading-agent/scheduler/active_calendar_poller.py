"""Shim module: monika.application.scheduler.active_calendar_poller."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.active_calendar_poller import *

_canonical = _importlib.import_module("monika.application.scheduler.active_calendar_poller")
_sys.modules[__name__] = _canonical
