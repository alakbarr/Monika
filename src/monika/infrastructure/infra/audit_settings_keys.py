"""
Backward-compatibility facade for audit_settings_keys script.
"""

import sys
import scripts.audit_settings_keys as _canonical

from scripts.audit_settings_keys import audit_keys, flatten_dict

__all__ = ["audit_keys", "flatten_dict"]

sys.modules[__name__] = _canonical
