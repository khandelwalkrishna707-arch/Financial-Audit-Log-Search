"""Build one clean Transaction from one validated row."""

from __future__ import annotations

from collections.abc import Mapping

from audit_search.models import Transaction
from audit_search.normalize.dates import normalize_date
from audit_search.normalize.fields import clean_text, normalize_action, parse_amount_cents


def to_transaction(row: Mapping[str, object], source_file: str | None = None) -> Transaction:
    """Normalize every field. Raises ValueError with a readable reason if a value is bad."""
    transaction_id = clean_text(row.get("transaction_id"))
    if transaction_id is None:
        raise ValueError("missing transaction_id")

    try:
        event_date = normalize_date(row.get("event_date"))
    except ValueError as exc:
        raise ValueError(f"bad event_date: {exc}") from None

    try:
        amount_cents = parse_amount_cents(row.get("amount"))
    except ValueError as exc:
        raise ValueError(f"bad amount: {exc}") from None

    return Transaction(
        transaction_id=transaction_id,
        event_date=event_date,
        account_id=clean_text(row.get("account_id")),
        action_type=normalize_action(row.get("action_type")),
        amount_cents=amount_cents,
        user_id=clean_text(row.get("user_id")),
        source_file=source_file,
    )
