"""Data classes shared by every layer, so all layers agree on field names and types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from audit_search.config import MAX_REJECTIONS_KEPT


@dataclass(frozen=True)
class Transaction:
    """One cleaned audit event, exactly as it is stored in the `audit_events` table.

    `event_date` is always ISO 8601 UTC text, e.g. "2026-03-14T09:30:00Z".
    `amount_cents` is the amount in whole cents (12.50 -> 1250), so money is never
    stored as a float and never picks up rounding errors.
    `action_type` is "" (not None) when unknown, because it is part of the duplicate key.
    """

    transaction_id: str
    event_date: str
    account_id: str | None = None
    action_type: str = ""
    amount_cents: int | None = None
    user_id: str | None = None
    source_file: str | None = None


@dataclass(frozen=True)
class RawRecord:
    """One record exactly as a parser read it, before any validation or cleaning.

    `location` says where it came from ("line 14", "record 3") for error messages.
    `error` is set when the parser already knows the row is broken (e.g. extra CSV columns).
    """

    location: str
    data: dict[str, Any]
    error: str | None = None


@dataclass(frozen=True)
class Rejection:
    location: str
    reason: str


@dataclass
class ImportSummary:
    """Counts reported to the user after an import."""

    source_file: str
    read: int = 0
    inserted: int = 0
    updated: int = 0
    skipped_duplicates: int = 0
    rejected: int = 0
    rejections: list[Rejection] = field(default_factory=list)

    @property
    def duplicates(self) -> int:
        return self.updated + self.skipped_duplicates

    def reject(self, location: str, reason: str) -> None:
        self.rejected += 1
        if len(self.rejections) < MAX_REJECTIONS_KEPT:
            self.rejections.append(Rejection(location, reason))
