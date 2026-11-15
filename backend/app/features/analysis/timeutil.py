"""Time helpers. The case clock is EST with a fixed -05:00 offset (CONTRACTS rule 7, CASE.md)."""
from datetime import date, datetime, time, timedelta, timezone

EST = timezone(timedelta(hours=-5), "EST")
BUSINESS_START = time(8, 0)
BUSINESS_END = time(18, 0)


def parse(t: str) -> datetime:
    """ISO 8601 -> aware datetime in EST. Naive input is assumed to be EST already."""
    dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=EST)
    return dt.astimezone(EST)


def local_day(dt: datetime) -> date:
    return dt.astimezone(EST).date()


def is_after_hours(dt: datetime) -> bool:
    d = dt.astimezone(EST)
    return d.weekday() >= 5 or not (BUSINESS_START <= d.time() < BUSINESS_END)


def spoken(dt: datetime) -> str:
    """How a person would say the time: '6:02 pm', '6:16:40 pm' when seconds matter."""
    d = dt.astimezone(EST)
    hour = d.hour % 12 or 12
    suffix = "am" if d.hour < 12 else "pm"
    if d.second:
        return f"{hour}:{d.minute:02d}:{d.second:02d} {suffix}"
    return f"{hour}:{d.minute:02d} {suffix}"
