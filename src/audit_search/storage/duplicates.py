"""The duplicate policy: what happens when an already-stored event is imported again.

* skip   -> keep the stored row, count the new one as a duplicate.
* update -> overwrite the stored row's details (account, amount, user, source file)
            with the new values, and count it as updated.

A "duplicate" means same transaction_id + event_date + action_type (see schema.sql).
Every statement uses `?` placeholders: values are never pasted into the SQL text.
"""

from __future__ import annotations

import sqlite3
from enum import Enum

from audit_search.models import Transaction


class Outcome(Enum):
    INSERTED = "inserted"
    UPDATED = "updated"
    SKIPPED = "skipped"


_INSERT_SQL = """
    INSERT INTO audit_events
        (transaction_id, event_date, account_id, action_type, amount_cents, user_id, source_file)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT (transaction_id, event_date, action_type) DO NOTHING
"""

_UPDATE_SQL = """
    UPDATE audit_events
       SET account_id = ?, amount_cents = ?, user_id = ?, source_file = ?
     WHERE transaction_id = ? AND event_date = ? AND action_type = ?
"""


def store(cursor: sqlite3.Cursor, tx: Transaction, policy: str) -> Outcome:
    """Insert one transaction, applying the duplicate policy. Returns what happened."""
    cursor.execute(
        _INSERT_SQL,
        (
            tx.transaction_id, tx.event_date, tx.account_id, tx.action_type,
            tx.amount_cents, tx.user_id, tx.source_file,
        ),
    )
    if cursor.rowcount == 1:
        return Outcome.INSERTED  # it was new

    # rowcount 0: the ON CONFLICT clause fired, so this event is already stored.
    if policy == "update":
        cursor.execute(
            _UPDATE_SQL,
            (
                tx.account_id, tx.amount_cents, tx.user_id, tx.source_file,
                tx.transaction_id, tx.event_date, tx.action_type,
            ),
        )
        return Outcome.UPDATED
    return Outcome.SKIPPED
