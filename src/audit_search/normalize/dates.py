"""Parse dates in many formats and convert them to ISO 8601 UTC: "YYYY-MM-DDTHH:MM:SSZ".

Why this matters: dates are stored as text. Because every stored date has the same
fixed-width UTC format, sorting the text alphabetically is the same as sorting by time,
so SQLite can use a normal B-tree index for date-range searches.

Rules (also documented in docs/date_formats.md):
  * A date WITH a timezone ("+05:30", "Z") is converted to UTC.
  * A date WITHOUT a timezone is assumed to already be UTC.
  * Slash/dash dates are DAY first: 03/04/2026 is 3 April 2026 (not March 4).
  * Fractional seconds are dropped (the stored precision is one second).
  * A number is a Unix timestamp (seconds or milliseconds), except an 8-digit number,
    which is YYYYMMDD. Numbers before March 1973 (such as 0) are rejected: in an audit
    log they are almost always a placeholder, not a real date.
"""

from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from decimal import Decimal

ISO_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# Tried in order after Python's own ISO parser has failed.
_FALLBACK_FORMATS = (
    "%Y-%m-%dT%H:%M:%S%z",  # 2026-03-14T09:30:00+0530 (no colon in offset)
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%d %H:%M:%S%z",
    "%d/%m/%Y %H:%M:%S",  # 14/03/2026 09:30:00
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%d-%m-%Y %H:%M:%S",  # 14-03-2026 09:30:00
    "%d-%m-%Y",
    "%Y/%m/%d %H:%M:%S",  # 2026/03/14 09:30:00
    "%Y/%m/%d",
    "%Y%m%d",  # 20260314
    "%d %B %Y",  # 14 March 2026  (Apache Fineract's default date format)
    "%d %b %Y",  # 14 Mar 2026
    "%d %B %Y %H:%M:%S",
    "%d %b %Y %H:%M:%S",
)

# Timestamps below this (3 March 1973) are rejected as unrealistic.
_MIN_EPOCH_SECONDS = 100_000_000
# Epoch numbers larger than this are milliseconds, not seconds.
_EPOCH_MS_THRESHOLD = 100_000_000_000


def normalize_date(value: object, assume_tz: tzinfo = timezone.utc) -> str:
    """Return `value` as "YYYY-MM-DDTHH:MM:SSZ". Raises ValueError if it is not a date."""
    moment = parse_datetime(value, assume_tz)
    return moment.astimezone(timezone.utc).strftime(ISO_UTC_FORMAT)


def parse_datetime(value: object, assume_tz: tzinfo = timezone.utc) -> datetime:
    """Turn a string, epoch number, date list or datetime into a timezone-aware datetime."""
    if value is None or isinstance(value, bool):
        raise ValueError("date is empty")

    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, (int, float, Decimal)):
        moment = _from_number(value)
    elif isinstance(value, (list, tuple)):
        moment = _from_parts(value)
    elif isinstance(value, str):
        moment = _from_string(value)
    else:
        raise ValueError(f"unsupported date type: {type(value).__name__}")

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=assume_tz)
    return moment


def _from_string(value: str) -> datetime:
    text = value.strip()
    if not text:
        raise ValueError("date is empty")

    # Unix timestamps written as text, e.g. "1773480600" (9+ digits; 8 digits is YYYYMMDD).
    if text.isascii() and text.isdigit() and len(text) >= 9:
        return _from_number(int(text))

    # Python's ISO parser. Python 3.10 does not understand a trailing "Z", so swap it.
    iso_text = text[:-1] + "+00:00" if text[-1] in "Zz" else text
    try:
        return datetime.fromisoformat(iso_text)
    except ValueError:
        pass

    for fmt in _FALLBACK_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    raise ValueError(f"impossible date or unknown format: {text!r}")


def _from_number(value: int | float | Decimal) -> datetime:
    if isinstance(value, int) and 10_000_000 <= value <= 99_999_999:
        return _from_string(str(value))  # 20260314 -> 14 March 2026, not a 1970 timestamp
    try:
        seconds = float(value)
    except OverflowError:
        raise ValueError(f"timestamp out of range: {value}") from None
    if seconds >= _EPOCH_MS_THRESHOLD:
        seconds /= 1000  # milliseconds -> seconds
    if not seconds >= _MIN_EPOCH_SECONDS:  # written as "not >=" so that NaN is caught too
        raise ValueError(f"number is not a realistic timestamp: {value}")
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        raise ValueError(f"timestamp out of range: {value}") from None


def _from_parts(parts: list | tuple) -> datetime:
    """Apache Fineract's JSON API sends dates as lists: [2026, 3, 14] or [2026, 3, 14, 9, 30, 0]."""
    if not 3 <= len(parts) <= 6 or not all(
        isinstance(p, int) and not isinstance(p, bool) for p in parts
    ):
        raise ValueError(f"unrecognised date list: {list(parts)!r}")
    try:
        return datetime(*parts)
    except (ValueError, OverflowError) as exc:  # OverflowError: e.g. year 10**20
        raise ValueError(f"invalid date {list(parts)!r}: {exc}") from None
