import pytest
from datetime import datetime, timezone, time as dtime
from utils.scheduling.wall_clock import next_occurrence, previous_occurrence, parse_time_list, get_tzinfo

def test_parse_time_list():
    times = parse_time_list(["07:00", "14:00", "19:00", "01:00"])
    assert len(times) == 4
    assert times[0] == dtime(1, 0)
    assert times[1] == dtime(7, 0)
    assert times[2] == dtime(14, 0)
    assert times[3] == dtime(19, 0)

def test_next_occurrence_same_day():
    tz = get_tzinfo('Asia/Jakarta')
    # Local time is 2026-08-19 12:00:00 (WIB) -> UTC is 05:00:00
    now_utc = datetime(2026, 8, 19, 5, 0, 0, tzinfo=timezone.utc)
    times = parse_time_list(["07:00", "14:00", "19:00", "01:00"])
    
    next_dt = next_occurrence(times, 'Asia/Jakarta', now_utc)
    next_local = next_dt.astimezone(tz)
    
    assert next_local.hour == 14
    assert next_local.minute == 0
    assert next_local.day == 19

def test_next_occurrence_rollover_next_day():
    tz = get_tzinfo('Asia/Jakarta')
    # Local time is 2026-08-19 23:00:00 (WIB) -> UTC is 16:00:00
    now_utc = datetime(2026, 8, 19, 16, 0, 0, tzinfo=timezone.utc)
    times = parse_time_list(["07:00", "14:00", "19:00", "01:00"])
    
    next_dt = next_occurrence(times, 'Asia/Jakarta', now_utc)
    next_local = next_dt.astimezone(tz)
    
    # Next should be 01:00 on the next day
    assert next_local.hour == 1
    assert next_local.minute == 0
    assert next_local.day == 20

def test_next_occurrence_before_midnight_utc():
    tz = get_tzinfo('Asia/Jakarta')
    # Local time is 2026-08-20 00:30:00 (WIB) -> UTC is 17:30:00 on 19th
    now_utc = datetime(2026, 8, 19, 17, 30, 0, tzinfo=timezone.utc)
    times = parse_time_list(["07:00", "14:00", "19:00", "01:00"])
    
    next_dt = next_occurrence(times, 'Asia/Jakarta', now_utc)
    next_local = next_dt.astimezone(tz)
    
    # Next should be 01:00 on the same local day (20th)
    assert next_local.hour == 1
    assert next_local.minute == 0
    assert next_local.day == 20


def test_previous_occurrence_at_night_rollover():
    tz = get_tzinfo('Asia/Jakarta')
    # Local time is 2026-08-20 03:00:00 (WIB) -> UTC is 2026-08-19 20:00:00
    now_utc = datetime(2026, 8, 19, 20, 0, 0, tzinfo=timezone.utc)
    times = parse_time_list(["07:00", "15:00", "20:00"])

    prev_dt = previous_occurrence(times, 'Asia/Jakarta', now_utc)
    prev_local = prev_dt.astimezone(tz)

    assert prev_local.hour == 20
    assert prev_local.minute == 0
    assert prev_local.day == 19


def test_previous_occurrence_during_day():
    tz = get_tzinfo('Asia/Jakarta')
    # Local time is 2026-08-20 14:30:00 (WIB) -> UTC is 2026-08-20 07:30:00
    now_utc = datetime(2026, 8, 20, 7, 30, 0, tzinfo=timezone.utc)
    times = parse_time_list(["07:00", "15:00", "20:00"])

    prev_dt = previous_occurrence(times, 'Asia/Jakarta', now_utc)
    prev_local = prev_dt.astimezone(tz)

    assert prev_local.hour == 7
    assert prev_local.minute == 0
    assert prev_local.day == 20


def test_previous_occurrence_exact_match():
    tz = get_tzinfo('Asia/Jakarta')
    # Local time is 2026-08-20 20:00:00 (WIB) -> UTC is 2026-08-20 13:00:00
    now_utc = datetime(2026, 8, 20, 13, 0, 0, tzinfo=timezone.utc)
    times = parse_time_list(["07:00", "15:00", "20:00"])

    prev_dt = previous_occurrence(times, 'Asia/Jakarta', now_utc)
    prev_local = prev_dt.astimezone(tz)

    assert prev_local.hour == 20
    assert prev_local.minute == 0
    assert prev_local.day == 20


def test_session_anchored_intervals():
    tz = get_tzinfo('Asia/Jakarta')
    times = parse_time_list(["07:00", "15:00", "20:00"])

    # 1. 07:00 WIB -> next is 15:00 WIB (8 hours)
    t1_utc = datetime(2026, 8, 20, 0, 0, 0, tzinfo=timezone.utc)  # 07:00 WIB
    next1 = next_occurrence(times, 'Asia/Jakarta', t1_utc)
    diff1_h = (next1 - t1_utc).total_seconds() / 3600
    assert diff1_h == 8.0

    # 2. 15:00 WIB -> next is 20:00 WIB (5 hours)
    t2_utc = datetime(2026, 8, 20, 8, 0, 0, tzinfo=timezone.utc)  # 15:00 WIB
    next2 = next_occurrence(times, 'Asia/Jakarta', t2_utc)
    diff2_h = (next2 - t2_utc).total_seconds() / 3600
    assert diff2_h == 5.0

    # 3. 20:00 WIB -> next is 07:00 WIB next day (11 hours)
    t3_utc = datetime(2026, 8, 20, 13, 0, 0, tzinfo=timezone.utc)  # 20:00 WIB
    next3 = next_occurrence(times, 'Asia/Jakarta', t3_utc)
    diff3_h = (next3 - t3_utc).total_seconds() / 3600
    assert diff3_h == 11.0


def test_previous_occurrence_empty_times_raises():
    import pytest
    with pytest.raises(ValueError, match="times_local cannot be empty"):
        previous_occurrence([])


def test_next_occurrence_empty_times_raises():
    import pytest
    with pytest.raises(ValueError, match="times_local cannot be empty"):
        next_occurrence([])
