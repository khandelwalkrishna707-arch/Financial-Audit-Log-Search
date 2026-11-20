"""Map the many possible column names onto our field names, and check required fields.

Different systems name the same column differently: "transactionId", "Transaction ID",
"txn_id"... `canonicalize()` maps all of them onto one name, e.g. `transaction_id`.
Matching ignores case, spaces, dashes and underscores. For each field the FIRST alias
found in the row wins, so an explicit "transaction_id" column beats a generic "id" column.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REQUIRED_FIELDS = ("transaction_id", "event_date")

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "transaction_id": ("transaction_id", "txn_id", "tx_id", "transaction_ref", "id"),
    "event_date": (
        "event_date", "transaction_date", "made_on_date", "timestamp",
        "created_at", "event_time", "date",
    ),
    "account_id": ("account_id", "account_no", "account_number", "account"),
    "action_type": ("action_type", "action_name", "transaction_type", "action", "type"),
    "amount": ("amount", "transaction_amount", "value"),
    "user_id": ("user_id", "maker_id", "made_by", "maker", "user"),
}


def _squash(name: str) -> str:
    """"Transaction ID" / "transactionId" / "transaction_id" -> "transactionid"."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


_SQUASHED_ALIASES = {
    field: tuple(_squash(alias) for alias in aliases) for field, aliases in FIELD_ALIASES.items()
}


def canonicalize(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Return a dict that uses our field names. Unknown columns are ignored."""
    by_squashed_name: dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(key, str):
            by_squashed_name.setdefault(_squash(key), value)

    row: dict[str, Any] = {}
    for field, aliases in _SQUASHED_ALIASES.items():
        for alias in aliases:
            if alias in by_squashed_name:
                row[field] = by_squashed_name[alias]
                break
    return row


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def missing_required(row: Mapping[str, Any]) -> list[str]:
    """Names of required fields that are absent or empty in an already-canonical row."""
    return [name for name in REQUIRED_FIELDS if _is_blank(row.get(name))]
