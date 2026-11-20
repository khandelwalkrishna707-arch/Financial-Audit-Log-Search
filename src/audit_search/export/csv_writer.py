"""CSV export. TODO (week 2): implement `write_csv`.

Requirements from the PRD:
  * Stable headers: always EXPORT_HEADERS, in this order, even when there are 0 results.
  * Proper quoting: use csv.writer, never ",".join(...). A value like "Smith, J" must not
    shift the columns.
  * Amounts: write cents_to_str(tx.amount_cents) so 1250 is exported as "12.50".
  * Write errors (folder missing, no permission, disk full) must give a clear message,
    not a Python traceback.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from audit_search.models import Transaction

EXPORT_HEADERS = (
    "transaction_id",
    "event_date",
    "account_id",
    "action_type",
    "amount",
    "user_id",
    "source_file",
)


def write_csv(transactions: Iterable[Transaction], path: str | Path) -> int:
    """Write the transactions to `path` and return how many rows were written."""
    raise NotImplementedError("TODO(week 2)")
