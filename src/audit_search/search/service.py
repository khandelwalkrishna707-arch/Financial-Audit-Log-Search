"""One search entry point shared by the CLI, the menu and the web UI.

It picks the right indexed query (exact ID, ID prefix or date range) and then applies the
optional filters, so no caller has to know about SQL.
"""

from __future__ import annotations

import sqlite3

from audit_search.models import Transaction
from audit_search.search.filters import Filters
from audit_search.search.queries import find_by_date_range, find_by_id, find_by_prefix


def search(
    conn: sqlite3.Connection,
    *,
    transaction_id: str | None = None,
    prefix: bool = False,
    start: str | None = None,
    end: str | None = None,
    filters: Filters | None = None,
) -> list[Transaction]:
    """Search by transaction ID OR by date range (both dates required), then filter.

    Raises ValueError for missing or invalid criteria.
    """
    has_id = bool(transaction_id)  # " " still counts, so find_by_id can say it is empty
    has_range = bool(start or end)
    if has_id and has_range:
        raise ValueError("search by transaction ID or by date range, not both")
    if has_id:
        finder = find_by_prefix if prefix else find_by_id
        results = finder(conn, transaction_id)
    elif has_range:
        if not start or not end:
            raise ValueError("a date range needs both a start and an end date")
        results = find_by_date_range(conn, start, end)
    else:
        raise ValueError("give a transaction ID or a date range")
    return filters.apply(results) if filters and filters.active else results
