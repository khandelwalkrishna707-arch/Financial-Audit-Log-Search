"""Search queries: transaction ID (exact or prefix) and inclusive date range.

Rules every query follows:
  * `?` placeholders for every value. SQL is written as constant strings, never built
    with f-strings, + or .format() (tests/unit/test_sql_safety.py enforces this).
  * Results are always sorted by event_date, transaction_id, action_type, so the same
    search always gives the same order.
  * Every query can use an index (checked by EXPLAIN QUERY PLAN in the tests):
      - ID and prefix searches use the UNIQUE (transaction_id, ...) index,
      - date searches use idx_tx_date.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, time, timedelta, timezone

from audit_search.models import Transaction
from audit_search.normalize.dates import ISO_UTC_FORMAT, normalize_date, parse_datetime

_BY_ID_SQL = """
    SELECT transaction_id, event_date, account_id, action_type, amount_cents, user_id, source_file
      FROM audit_events
     WHERE transaction_id = ?
     ORDER BY event_date, transaction_id, action_type
"""

# A prefix search is a RANGE search: every ID that starts with "TX-98" sorts at or after
# "TX-98" and before "TX-99". Unlike LIKE, this uses the index and has no wildcards.
_BY_PREFIX_SQL = """
    SELECT transaction_id, event_date, account_id, action_type, amount_cents, user_id, source_file
      FROM audit_events
     WHERE transaction_id >= ? AND transaction_id < ?
     ORDER BY event_date, transaction_id, action_type
"""

# Half-open range [start, end_exclusive): see date_range_bounds() for why.
_BY_DATE_RANGE_SQL = """
    SELECT transaction_id, event_date, account_id, action_type, amount_cents, user_id, source_file
      FROM audit_events
     WHERE event_date >= ? AND event_date < ?
     ORDER BY event_date, transaction_id, action_type
"""

_LAST_UNICODE_CHAR = 0x10FFFF
_SURROGATES = range(0xD800, 0xE000)  # cannot appear in stored text, so skip over them


def row_to_transaction(row: sqlite3.Row) -> Transaction:
    """Build a Transaction from a database row (columns have the same names as the fields)."""
    values = dict(row)
    values.pop("id", None)
    return Transaction(**values)


def find_by_id(conn: sqlite3.Connection, transaction_id: str) -> list[Transaction]:
    """All events whose transaction_id is EXACTLY `transaction_id` (case-sensitive)."""
    wanted = transaction_id.strip()
    if not wanted:
        raise ValueError("transaction ID must not be empty")
    return _run(conn, _BY_ID_SQL, (wanted,))


def find_by_prefix(conn: sqlite3.Connection, prefix: str) -> list[Transaction]:
    """All events whose transaction_id STARTS WITH `prefix` (e.g. "TX-98" finds "TX-98721").

    `%` and `_` are ordinary characters here, not wildcards.
    """
    start = prefix.strip()
    if not start:
        raise ValueError("prefix must not be empty")
    return _run(conn, _BY_PREFIX_SQL, (start, _prefix_upper_bound(start)))


def find_by_date_range(conn: sqlite3.Connection, start: str, end: str) -> list[Transaction]:
    """All events from `start` to `end`, BOTH included. Accepts any format dates.py accepts."""
    return _run(conn, _BY_DATE_RANGE_SQL, date_range_bounds(start, end))


def date_range_bounds(start: str, end: str) -> tuple[str, str]:
    """Turn the user's inclusive range into a half-open one: (start, end_exclusive).

    Why: `--to 2026-03-31` normalizes to 2026-03-31T00:00:00Z, the very START of that day.
    `BETWEEN` would then miss everything later on March 31. So:
      * a date without a time  -> end_exclusive is the next day at 00:00:00Z
      * a date with a time      -> end_exclusive is one second later (stored dates have
                                   one-second precision, so that second is included)
    """
    try:
        start_iso = normalize_date(start)
    except ValueError as exc:
        raise ValueError(f"bad start date: {exc}") from None
    try:
        end_moment = parse_datetime(end).astimezone(timezone.utc).replace(microsecond=0)
    except ValueError as exc:
        raise ValueError(f"bad end date: {exc}") from None

    step = timedelta(days=1) if _is_date_only(end, end_moment) else timedelta(seconds=1)
    end_exclusive = (end_moment + step).strftime(ISO_UTC_FORMAT)

    if start_iso >= end_exclusive:
        raise ValueError(f"start date {start!r} is after end date {end!r}")
    return start_iso, end_exclusive


def _is_date_only(text: str, moment: datetime) -> bool:
    """True for inputs like "2026-03-31", "31/03/2026" or "20260331" (no time written)."""
    is_epoch = text.strip().isdigit() and len(text.strip()) >= 9
    return moment.time() == time(0, 0) and ":" not in text and not is_epoch


def _prefix_upper_bound(prefix: str) -> str:
    """The first string that sorts after every string starting with `prefix`.

    "TX-98" -> "TX-99"; "AB~" -> "AB\x7f". Text is compared by Unicode code point,
    which is the same order SQLite uses for UTF-8 text.
    """
    code = ord(prefix[-1]) + 1
    if code in _SURROGATES:
        code = _SURROGATES.stop
    if code > _LAST_UNICODE_CHAR:
        raise ValueError("prefix ends with an unsupported character")
    return prefix[:-1] + chr(code)


def _run(conn: sqlite3.Connection, sql: str, params: tuple[str, ...]) -> list[Transaction]:
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row  # rows readable by column name, on any connection
    return [row_to_transaction(row) for row in cursor.execute(sql, params)]
