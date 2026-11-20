"""Ingestion layer: read audit log files lazily and check each row."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from audit_search.ingest.csv_parser import iter_csv
from audit_search.ingest.json_parser import iter_json, iter_jsonl
from audit_search.models import RawRecord

_PARSERS = {
    ".csv": iter_csv,
    ".json": iter_json,
    ".jsonl": iter_jsonl,
    ".ndjson": iter_jsonl,
}

SUPPORTED_EXTENSIONS = tuple(_PARSERS)


def iter_records(path: str | Path) -> Iterator[RawRecord]:
    """Pick the right parser from the file extension and stream its records."""
    path = Path(path)
    parser = _PARSERS.get(path.suffix.lower())
    if parser is None:
        supported = ", ".join(SUPPORTED_EXTENSIONS)
        raise ValueError(f"unsupported file type {path.suffix!r} (supported: {supported})")
    return parser(path)
