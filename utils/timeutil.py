"""
utils/timeutil.py — India Standard Time helpers.

The shop operates in India (Kalaburagi, IST = UTC+05:30, no daylight saving).
Servers such as Render run in UTC, so `datetime.now()` / `utcnow()` give a
clock that is 5h30m behind the shop. Every timestamp the app stores or shows
goes through these helpers so bills always carry the real Indian time,
regardless of the server's or the laptop's timezone setting.

Values are returned as naive datetimes holding IST wall-clock time, which is
what the existing DateTime columns, `func.date()` grouping and date-range
filters already expect.
"""

from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def now_ist() -> datetime:
    """Current Indian time as a naive datetime."""
    return datetime.now(IST).replace(tzinfo=None)


def today_ist() -> date:
    """Today's date in India."""
    return now_ist().date()
