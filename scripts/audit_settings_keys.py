#!/usr/bin/env python3
"""
Audit queried settings keys in codebase against config/settings.yaml.
"""

from __future__ import annotations

from monika.infrastructure.infra.audit_settings_keys import audit_keys, flatten_dict

__all__ = ["audit_keys", "flatten_dict"]

if __name__ == "__main__":
    audit_keys()
