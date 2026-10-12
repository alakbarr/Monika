"""
Compatibility facade shim for legacy streaming_lease.py.
Re-exports from canonical monika.core.streaming.streaming_lease.
"""

from __future__ import annotations

import monika.core.streaming.streaming_lease as _canonical

from monika.core.streaming.streaming_lease import (
    LeaseAcquisitionTimeoutError,
    LeaseExpiredOrInvalidError,
    LeaseRecord,
    StreamWriterLeaseCoordinator,
    StreamWriterLeaseHandle,
    get_stream_lease_coordinator,
)

__all__ = ['LeaseAcquisitionTimeoutError', 'LeaseExpiredOrInvalidError', 'LeaseRecord', 'StreamWriterLeaseCoordinator', 'StreamWriterLeaseHandle', 'get_stream_lease_coordinator']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
