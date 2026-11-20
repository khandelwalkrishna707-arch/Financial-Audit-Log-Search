"""Terminal table output. TODO (week 2): implement `format_table`.

Example of the expected output:

    transaction_id  event_date            action_type  amount   account_id
    --------------  --------------------  -----------  -------  ----------
    TX-000123       2026-03-14T09:30:00Z  DEPOSIT      1250.00  AC-1001
    1 result

Tip: work out each column's width as max(len(header), longest value), then use str.ljust().
Right-align the amount column with str.rjust() so the decimal points line up.
"""

from __future__ import annotations

from collections.abc import Sequence

from audit_search.models import Transaction


def format_table(transactions: Sequence[Transaction]) -> str:
    """Return the transactions as an aligned text table, or "No results." when empty."""
    raise NotImplementedError("TODO(week 2)")
