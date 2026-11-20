"""Terminal table output.

Example:

    transaction_id  event_date            action_type   amount  account_id  user_id
    --------------  --------------------  -----------  -------  ----------  -------
    TX-000123       2026-03-14T09:30:00Z  DEPOSIT      1250.00  AC-1001     U-7
    1 result

Each column is as wide as its header or its longest value. The amount column is
right-aligned so the decimal points line up.
"""

from __future__ import annotations

from collections.abc import Sequence

from audit_search.export.style import ACTION_COLORS, paint
from audit_search.models import Transaction
from audit_search.normalize.fields import cents_to_str

TABLE_HEADERS = ("transaction_id", "event_date", "action_type", "amount", "account_id", "user_id")
_RIGHT_ALIGNED = {"amount"}
_MISSING = "-"


def _cells(tx: Transaction) -> tuple[str, ...]:
    values = (
        tx.transaction_id,
        tx.event_date,
        tx.action_type,
        cents_to_str(tx.amount_cents),
        tx.account_id,
        tx.user_id,
    )
    return tuple(value or _MISSING for value in values)


def result_count(count: int) -> str:
    return f"{count} result{'s' if count != 1 else ''}"


def format_table(transactions: Sequence[Transaction], color: bool = False) -> str:
    """Return the transactions as an aligned text table, or "No results." when empty.

    With color=True the header, separators, action types and negative amounts are colored;
    the layout is identical either way (colors are added after padding).
    """
    if not transactions:
        return paint("No results.", "yellow", enabled=color)
    rows = [_cells(tx) for tx in transactions]
    widths = [
        max(len(header), *(len(row[i]) for row in rows)) for i, header in enumerate(TABLE_HEADERS)
    ]

    def pad(header: str, cell: str, width: int) -> str:
        return cell.rjust(width) if header in _RIGHT_ALIGNED else cell.ljust(width)

    def cell_style(header: str, cell: str) -> tuple[str, ...]:
        if cell == _MISSING:
            return ("dim",)
        if header == "transaction_id":
            return ("bold",)
        if header == "action_type":
            return (ACTION_COLORS.get(cell, "cyan"),)
        if header == "amount" and cell.startswith("-"):
            return ("red",)
        if header == "event_date":
            return ("dim",)
        return ()

    def line(cells: Sequence[str], styles=None) -> str:
        parts = []
        for header, cell, width in zip(TABLE_HEADERS, cells, widths, strict=True):
            text = pad(header, cell, width)
            if header == TABLE_HEADERS[-1]:
                text = text.rstrip()  # no trailing spaces, colored or not
            style = styles or cell_style(header, cell)
            parts.append(paint(text, *style, enabled=color))
        return "  ".join(parts).rstrip()

    lines = [line(TABLE_HEADERS, ("bold", "cyan")),
             line(["-" * w for w in widths], ("dim",))]
    lines.extend(line(row) for row in rows)
    lines.append(paint(result_count(len(rows)), "bold", enabled=color))
    return "\n".join(lines)
