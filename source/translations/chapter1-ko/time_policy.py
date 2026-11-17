"""DeepSeek peak/off-peak billing clock.

Official policy as checked on 2026-11-06:
Peak hours are 01:00-04:00 and 06:00-10:00 UTC, Monday through Friday,
excluding Chinese public holidays. Everything else is off-peak.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any


UTC = timezone.utc
KST = timezone(timedelta(hours=9), "KST")
PEAK_WINDOWS_UTC = ((time(1, 0), time(4, 0)), (time(6, 0), time(10, 0)))
POLICY_SOURCE = "https://api-docs.deepseek.com/quick_start/pricing"
POLICY_CHECKED_AT = "2026-11-06"


def _at(day: datetime, value: time) -> datetime:
    return datetime.combine(day.date(), value, tzinfo=UTC)


def _format_local(value: datetime) -> str:
    local = value.astimezone(KST)
    return local.strftime("%m/%d %H:%M KST")


def _is_peak_time(utc_now: datetime, holiday: bool) -> bool:
    if holiday or utc_now.weekday() >= 5:
        return False
    current = utc_now.timetz().replace(tzinfo=None)
    return any(start <= current < end for start, end in PEAK_WINDOWS_UTC)


def _next_peak_start(utc_now: datetime, holiday: bool) -> datetime:
    for day_offset in range(0, 8):
        day = utc_now + timedelta(days=day_offset)
        if day.weekday() >= 5 or (holiday and day_offset == 0):
            continue
        for start, end in PEAK_WINDOWS_UTC:
            candidate = _at(day, start)
            if candidate > utc_now:
                return candidate
    return utc_now + timedelta(days=7)


def market_clock(now: datetime | None = None, holiday: bool = False) -> dict[str, Any]:
    utc_now = (now or datetime.now(tz=UTC)).astimezone(UTC)
    peak = _is_peak_time(utc_now, holiday)
    if peak:
        end_time = next(
            end
            for start, end in PEAK_WINDOWS_UTC
            if _at(utc_now, start) <= utc_now < _at(utc_now, end)
        )
        transition = _at(utc_now, end_time)
        transition_label = "오프피크 시작"
        period = "peak"
        remaining = max(0, int((transition - utc_now).total_seconds()))
    else:
        transition = _next_peak_start(utc_now, holiday)
        transition_label = "다음 피크 시작"
        period = "off_peak"
        remaining = max(0, int((transition - utc_now).total_seconds()))
    return {
        "period": period,
        "is_peak": peak,
        "transition_label": transition_label,
        "transition_at": transition.isoformat(),
        "transition_at_kst": _format_local(transition),
        "remaining_seconds": remaining,
        "local_now": utc_now.astimezone(KST).isoformat(timespec="seconds"),
        "holiday_override": holiday,
        "source": POLICY_SOURCE,
        "checked_at": POLICY_CHECKED_AT,
    }


def format_countdown(seconds: int) -> str:
    seconds = max(0, int(seconds))
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    if days:
        return f"{days}일 {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def period_for_timestamp(value: str | datetime | None) -> str:
    if isinstance(value, datetime):
        moment = value
    elif value:
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            moment = datetime.now(tz=UTC)
    else:
        moment = datetime.now(tz=UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return "peak" if _is_peak_time(moment.astimezone(UTC), False) else "off_peak"
