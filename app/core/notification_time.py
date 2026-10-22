"""Calendar and wall-clock helpers for stable timezone/DST reminder scheduling."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def local_datetime(day: date, at: time, zone: ZoneInfo) -> datetime:
    """Resolve wall time; ambiguous times use the first fold, gaps shift forward."""
    naive = datetime.combine(day, at.replace(tzinfo=None))
    for minute in range(181):
        candidate_naive = naive + timedelta(minutes=minute)
        candidate = candidate_naive.replace(tzinfo=zone, fold=0)
        if candidate.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == candidate_naive:
            return candidate.astimezone(timezone.utc)
    raise ValueError("Could not resolve the configured local reminder time.")


def quiet_adjust(day: date, at: time, start: time | None, end: time | None) -> tuple[date, time]:
    if start is None or end is None or start == end:
        return day, at
    now_min = at.hour * 60 + at.minute
    start_min = start.hour * 60 + start.minute
    end_min = end.hour * 60 + end.minute
    if start_min < end_min:
        quiet = start_min <= now_min < end_min
        return (day, end) if quiet else (day, at)
    if now_min >= start_min:
        return day + timedelta(days=1), end
    if now_min < end_min:
        return day, end
    return day, at


def safe_now(value: datetime | None = None) -> datetime:
    """Return an aware UTC instant; naive database timestamps are UTC by convention."""
    value = value or datetime.now(timezone.utc)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
