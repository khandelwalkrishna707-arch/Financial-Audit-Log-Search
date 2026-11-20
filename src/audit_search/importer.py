"""The import pipeline: read -> validate -> normalize -> store in batches -> summary.

This is the "left path" of the workflow diagram in the PRD. The CLI and the menu both call
`import_file`, so the import logic lives in exactly one place.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from audit_search.config import BATCH_SIZE, DEFAULT_DUPLICATE_POLICY
from audit_search.ingest import iter_records
from audit_search.ingest.validator import canonicalize, missing_required
from audit_search.models import ImportSummary, Transaction
from audit_search.normalize.record import to_transaction
from audit_search.storage.database import insert_batch
from audit_search.storage.duplicates import Outcome


def import_file(
    conn: sqlite3.Connection,
    path: str | Path,
    policy: str = DEFAULT_DUPLICATE_POLICY,
    batch_size: int = BATCH_SIZE,
) -> ImportSummary:
    """Import one CSV / JSON / JSONL file and return what happened.

    Bad ROWS are rejected and counted; the import carries on.
    A bad FILE (not found, unreadable, broken JSON array) raises an exception. Batches
    already saved stay saved, and re-importing is safe because duplicates are detected.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"file not found: {path}")

    summary = ImportSummary(source_file=path.name)
    batch: list[Transaction] = []

    def flush() -> None:
        outcomes = insert_batch(conn, batch, policy)
        summary.inserted += outcomes[Outcome.INSERTED]
        summary.updated += outcomes[Outcome.UPDATED]
        summary.skipped_duplicates += outcomes[Outcome.SKIPPED]
        batch.clear()

    for raw in iter_records(path):
        summary.read += 1
        if raw.error:
            summary.reject(raw.location, raw.error)
            continue

        row = canonicalize(raw.data)
        missing = missing_required(row)
        if missing:
            summary.reject(raw.location, "missing " + ", ".join(missing))
            continue

        try:
            batch.append(to_transaction(row, source_file=path.name))
        except ValueError as exc:
            summary.reject(raw.location, str(exc))
            continue

        if len(batch) >= batch_size:
            flush()

    if batch:
        flush()
    return summary
