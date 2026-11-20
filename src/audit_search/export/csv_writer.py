"""CSV export with stable headers.

Rules (PRD):
  * Stable headers: always EXPORT_HEADERS, in this order, even when there are 0 results.
  * Proper quoting through csv.writer, so a value like "Smith, J" never shifts the columns.
  * Amounts are written with cents_to_str(), so 1250 is exported as "12.50".
  * Write errors (folder missing, no permission, disk full) raise ExportError with a clear
    message the CLI can print, instead of a traceback.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from audit_search.models import Transaction
from audit_search.normalize.fields import cents_to_str

EXPORT_HEADERS = (
    "transaction_id",
    "event_date",
    "account_id",
    "action_type",
    "amount",
    "user_id",
    "source_file",
)


class ExportError(Exception):
    """The CSV file could not be written."""


def transaction_to_row(tx: Transaction) -> list[str]:
    """One CSV row, in EXPORT_HEADERS order. Missing values become empty cells."""
    return [
        tx.transaction_id,
        tx.event_date,
        tx.account_id or "",
        tx.action_type or "",
        cents_to_str(tx.amount_cents) or "",
        tx.user_id or "",
        tx.source_file or "",
    ]


def write_rows(transactions: Iterable[Transaction], stream) -> int:
    """Write the header and rows to an open text stream. Return the number of data rows."""
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(EXPORT_HEADERS)
    count = 0
    for tx in transactions:
        writer.writerow(transaction_to_row(tx))
        count += 1
    return count


def write_csv(transactions: Iterable[Transaction], path: str | Path) -> int:
    """Write the transactions to `path` and return how many rows were written."""
    target = Path(path)
    try:
        with target.open("w", encoding="utf-8", newline="") as handle:
            return write_rows(transactions, handle)
    except OSError as exc:
        reason = exc.strerror or str(exc)
        raise ExportError(f"could not write {target}: {reason}") from None
