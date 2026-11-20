"""Search queries. TODO (week 2): implement these functions.

Rules every query must follow:
  * Use `?` placeholders for every value. Never build SQL with f-strings, + or .format().
    (tests/unit/test_sql_safety.py fails the build if you do.)
  * Sort results with ORDER BY event_date, transaction_id so the output is always the same.
  * Turn each sqlite3.Row into a Transaction (see `row_to_transaction`).

Read docs/remaining_work.md first: it explains the two traps (prefix search and the end date).
"""

from __future__ import annotations

import sqlite3

from audit_search.models import Transaction


def row_to_transaction(row: sqlite3.Row) -> Transaction:
    """Build a Transaction from a database row (columns have the same names as the fields)."""
    raise NotImplementedError("TODO(week 2)")


def find_by_id(conn: sqlite3.Connection, transaction_id: str) -> list[Transaction]:
    """All events whose transaction_id is EXACTLY `transaction_id`."""
    raise NotImplementedError("TODO(week 2)")


def find_by_prefix(conn: sqlite3.Connection, prefix: str) -> list[Transaction]:
    """All events whose transaction_id STARTS WITH `prefix` (e.g. "TX-98" finds "TX-98721")."""
    raise NotImplementedError("TODO(week 2)")


def find_by_date_range(conn: sqlite3.Connection, start: str, end: str) -> list[Transaction]:
    """All events from `start` to `end`, both days INCLUDED. Accepts any format dates.py accepts."""
    raise NotImplementedError("TODO(week 2)")
