# ==============================================================================
# Package: monika.application.scheduler
# File: universal_cron_scheduler.py
# ==============================================================================

"""
Canonical forwarder and compatibility facade for UniversalCronScheduler.
Directs all scheduling calls to the modern UnifiedCronEngine, eliminating
schema collision and dual-database corruption on data/universal_cron.db.
"""

from monika.application.scheduler.unified_cron_engine import (
    DEFAULT_CRON_DB,
    CronJob,
    DeliveryStatus,
    UnifiedCronEngine,
    UnifiedCronJob,
    UniversalCronScheduler,
    compute_next_cron_timestamp,
    get_unified_cron_engine,
)

__all__ = [
    "DEFAULT_CRON_DB",
    "CronJob",
    "DeliveryStatus",
    "UnifiedCronJob",
    "UnifiedCronEngine",
    "UniversalCronScheduler",
    "compute_next_cron_timestamp",
    "get_unified_cron_engine",
]
