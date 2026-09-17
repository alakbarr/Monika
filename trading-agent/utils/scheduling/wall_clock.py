"""
utils/scheduling/wall_clock.py

Wall-clock ("jadwal jam tetap") scheduling helpers.

Masalah yang diselesaikan: beberapa loop background di sistem ini langsung
menjalankan pekerjaan mahal (AI Stage1+Stage2) begitu proses start,
lalu baru tidur N jam sebelum jalan lagi. Karena agent sering di-restart
saat development, setiap restart memicu satu siklus analisis penuh yang
mahal — memboroskan budget API tanpa manfaat.

Modul ini memungkinkan sebuah loop untuk bilang "jalankan pada jam-jam
tertentu setiap hari, di timezone ini" (mis. WIB / Asia/Jakarta), lalu
cukup tidur sampai jam berikutnya — berapa kali pun proses di-restart di
antaranya.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Sequence, Optional

logger = logging.getLogger('TradingAgent.WallClockScheduler')

_FIXED_OFFSETS_HOURS = {
    'Asia/Jakarta': 7,    # WIB
    'Asia/Makassar': 8,   # WITA
    'Asia/Jayapura': 9,   # WIT
    'UTC': 0,
}


def get_tzinfo(tz_name: str):
    """
    Return a tzinfo object for `tz_name`. Prefers stdlib `zoneinfo` (IANA
    tz database); falls back to a fixed UTC offset if the tz database is
    unavailable (e.g. some Windows installs tanpa paket `tzdata`). WIB
    tidak punya DST, jadi fallback fixed-offset tetap 100% akurat untuk
    kasus penggunaan ini.
    """
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)
    except Exception:
        offset_hours = _FIXED_OFFSETS_HOURS.get(tz_name)
        if offset_hours is None:
            if tz_name in ("Asia/Jakarta", "Asia/Pontianak", "WIB", "UTC+7", "GMT+7"):
                offset_hours = 7
            else:
                logger.warning(
                    f"[WallClockScheduler] Timezone '{tz_name}' tidak dikenal atau "
                    f"zoneinfo/tzdata tidak tersedia — fallback ke UTC."
                )
                offset_hours = 0
        return timezone(timedelta(hours=offset_hours))


def parse_time_list(times: Sequence[str]) -> list[dtime]:
    """Parse ['07:00', '14:00', ...] (format 24 jam HH:MM, waktu lokal) menjadi list[time] terurut."""
    parsed = []
    for t in times:
        t = str(t).strip()
        hh, mm = t.split(':')
        parsed.append(dtime(hour=int(hh), minute=int(mm)))
    if not parsed:
        raise ValueError('Minimal satu jam terjadwal harus dikonfigurasi.')
    return sorted(parsed)


def next_occurrence(
    times_local: Sequence[dtime],
    tz_name: str = 'Asia/Jakarta',
    now_utc: datetime | None = None,
) -> datetime:
    """
    Dari daftar jam lokal harian, kembalikan kejadian berikutnya (sebagai
    datetime UTC tz-aware) yang berada strictly setelah `now_utc`.
    """
    if not times_local:
        raise ValueError('times_local cannot be empty.')
    tz = get_tzinfo(tz_name)
    now_utc = now_utc or datetime.now(timezone.utc)
    now_local = now_utc.astimezone(tz)

    candidates = []
    for day_offset in (0, 1):
        target_date = (now_local + timedelta(days=day_offset)).date()
        for t in times_local:
            candidate_local = datetime.combine(target_date, t, tzinfo=tz)
            if candidate_local > now_local:
                candidates.append(candidate_local)
    candidates.sort()
    next_local = candidates[0]
    return next_local.astimezone(timezone.utc)


def previous_occurrence(
    times_local: Sequence[dtime],
    tz_name: str = 'Asia/Jakarta',
    now_utc: datetime | None = None,
) -> datetime:
    """
    Dari daftar jam lokal harian, kembalikan kejadian terjadwal terakhir
    (sebagai datetime UTC tz-aware) yang berada <= `now_utc`.
    """
    if not times_local:
        raise ValueError('times_local cannot be empty.')
    tz = get_tzinfo(tz_name)
    now_utc = now_utc or datetime.now(timezone.utc)
    now_local = now_utc.astimezone(tz)

    candidates = []
    for day_offset in (-1, 0):
        target_date = (now_local + timedelta(days=day_offset)).date()
        for t in times_local:
            candidate_local = datetime.combine(target_date, t, tzinfo=tz)
            if candidate_local <= now_local:
                candidates.append(candidate_local)
    candidates.sort()
    prev_local = candidates[-1]
    return prev_local.astimezone(timezone.utc)


async def sleep_until_next(
    times_local: Sequence[dtime],
    tz_name: str = 'Asia/Jakarta',
    label: str = 'task',
    shutdown_event: Optional[asyncio.Event] = None,
) -> datetime:
    """Tidur sampai jam terjadwal berikutnya tiba atau shutdown_event diset. Mengembalikan target datetime (UTC)."""
    target = next_occurrence(times_local, tz_name)
    now = datetime.now(timezone.utc)
    wait_seconds = max(0.0, (target - now).total_seconds())
    tz = get_tzinfo(tz_name)
    logger.info(
        f"[{label}] Jadwal berikutnya: {target.astimezone(tz).strftime('%Y-%m-%d %H:%M')} {tz_name} "
        f"({target.strftime('%Y-%m-%d %H:%M UTC')}) — tidur {wait_seconds / 3600:.2f} jam "
        f"({wait_seconds / 60:.0f} menit)"
    )
    if wait_seconds > 0:
        if shutdown_event is not None:
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=wait_seconds)
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(wait_seconds)
    return target
