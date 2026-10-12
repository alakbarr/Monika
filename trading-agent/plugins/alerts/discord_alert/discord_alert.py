"""Shim module: monika.application.plugins.alerts.discord_alert.discord_alert."""

import sys as _sys
import importlib as _importlib

from monika.application.plugins.alerts.discord_alert.discord_alert import *

_canonical = _importlib.import_module("monika.application.plugins.alerts.discord_alert.discord_alert")
_sys.modules[__name__] = _canonical
