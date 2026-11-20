"""Optional filters applied on top of an ID or date-range search.

The indexed query (search/queries.py) narrows the rows first; these filters then keep only
the matching ones in Python. That keeps every SQL statement constant and parameterized,
and the result sets after an indexed lookup are small enough that this costs very little.

Amounts are compared in cents, so "--min-amount 10.50" means amount_cents >= 1050.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from audit_search.models import Transaction
from audit_search.normalize.fields import clean_text, normalize_action, parse_amount_cents


@dataclass(frozen=True)
class Filters:
    account_id: str | None = None
    user_id: str | None = None
    action_type: str | None = None
    min_cents: int | None = None
    max_cents: int | None = None

    @classmethod
    def from_text(
        cls,
        account_id: str | None = None,
        user_id: str | None = None,
        action_type: str | None = None,
        min_amount: str | None = None,
        max_amount: str | None = None,
    ) -> Filters:
        """Build filters from user input (CLI, menu or web form). Raises ValueError."""
        try:
            min_cents = parse_amount_cents(min_amount)
        except ValueError as exc:
            raise ValueError(f"bad minimum amount: {exc}") from None
        try:
            max_cents = parse_amount_cents(max_amount)
        except ValueError as exc:
            raise ValueError(f"bad maximum amount: {exc}") from None
        if min_cents is not None and max_cents is not None and min_cents > max_cents:
            raise ValueError("minimum amount is larger than maximum amount")
        return cls(
            account_id=clean_text(account_id),
            user_id=clean_text(user_id),
            action_type=normalize_action(action_type) or None,
            min_cents=min_cents,
            max_cents=max_cents,
        )

    @property
    def active(self) -> bool:
        return any(v is not None for v in (self.account_id, self.user_id, self.action_type,
                                           self.min_cents, self.max_cents))

    def matches(self, tx: Transaction) -> bool:
        if self.account_id is not None and tx.account_id != self.account_id:
            return False
        if self.user_id is not None and tx.user_id != self.user_id:
            return False
        if self.action_type is not None and tx.action_type != self.action_type:
            return False
        if self.min_cents is not None and (tx.amount_cents is None
                                           or tx.amount_cents < self.min_cents):
            return False
        return not (self.max_cents is not None
                    and (tx.amount_cents is None or tx.amount_cents > self.max_cents))

    def apply(self, transactions: Iterable[Transaction]) -> list[Transaction]:
        return [tx for tx in transactions if self.matches(tx)]
