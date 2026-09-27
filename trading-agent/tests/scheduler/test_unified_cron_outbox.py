# ==============================================================================
# File: tests/scheduler/test_unified_cron_outbox.py
# Monika Unified Cron Outbox Delivery Lease Test Suite
# ==============================================================================

import time
import pytest
from scheduler.unified_cron_engine import (
    UnifiedCronEngine,
    DeliveryStatus,
    UnifiedCronJob,
)


@pytest.fixture
def engine(tmp_path):
    db_file = tmp_path / "test_cron.db"
    return UnifiedCronEngine(db_path=str(db_file))


def test_enqueue_and_acquire_outbox_lease(engine):
    del_id = engine.enqueue_outbox_delivery(
        job_id="job_macro_brief",
        channel="telegram",
        destination="-10012345678",
        payload="Premarket Briefing Ready",
    )
    assert del_id.startswith("del_")

    # Acquire lease
    leased = engine.acquire_outbox_lease(batch_size=5, lease_seconds=60.0)
    assert len(leased) == 1
    assert leased[0]["delivery_id"] == del_id
    assert leased[0]["status"] == DeliveryStatus.SENDING
    assert leased[0]["channel"] == "telegram"
    assert leased[0]["payload"] == "Premarket Briefing Ready"

    # Subsequent immediate acquire finds nothing (lease is active)
    leased_again = engine.acquire_outbox_lease(batch_size=5, lease_seconds=60.0)
    assert len(leased_again) == 0


def test_outbox_mark_sent(engine):
    del_id = engine.enqueue_outbox_delivery(
        job_id="job_test",
        channel="discord",
        destination="webhook_url",
        payload="Test message",
    )
    leased = engine.acquire_outbox_lease(batch_size=1)
    assert len(leased) == 1

    engine.mark_outbox_sent(del_id)

    # Leased again finds nothing (status is SENT)
    leased_after = engine.acquire_outbox_lease(batch_size=1)
    assert len(leased_after) == 0


def test_outbox_lease_expiry_and_retry(engine):
    del_id = engine.enqueue_outbox_delivery(
        job_id="job_fail",
        channel="telegram",
        destination="chat_1",
        payload="Failed first attempt",
    )
    # Acquire lease with 0.1s expiry
    leased = engine.acquire_outbox_lease(batch_size=1, lease_seconds=0.1)
    assert len(leased) == 1

    time.sleep(0.2)

    # Since lease expired, acquiring lease picks it up again
    reacquired = engine.acquire_outbox_lease(batch_size=1, lease_seconds=60.0)
    assert len(reacquired) == 1
    assert reacquired[0]["delivery_id"] == del_id


def test_dispatch_job_uses_outbox(engine):
    delivered_msgs = []

    def mock_dispatcher(job, output):
        delivered_msgs.append((job.target_delivery, output))

    engine.set_channel_dispatcher(mock_dispatcher)

    job = UnifiedCronJob(
        job_id="macro_alert",
        schedule_expression="hourly",
        prompt="echo alert",
        target_delivery="telegram",
        target_destination="channel_alert",
        no_agent=True,
    )

    engine._dispatch_job(job)

    assert len(delivered_msgs) == 1
    assert delivered_msgs[0][0] == "telegram"

    # Check that outbox has recorded this delivery as SENT
    conn = engine._get_conn() if hasattr(engine, "_get_conn") else None
    import sqlite3
    c = sqlite3.connect(engine.db_path)
    cur = c.cursor()
    cur.execute("SELECT status FROM outbox_deliveries WHERE job_id = ?", ("macro_alert",))
    rows = cur.fetchall()
    c.close()
    assert len(rows) == 1
    assert rows[0][0] == DeliveryStatus.SENT
