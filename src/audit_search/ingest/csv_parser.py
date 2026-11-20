"""Stream a CSV file one row at a time, so a huge file never has to fit in memory."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

from audit_search.models import RawRecord


def iter_csv(path: str | Path) -> Iterator[RawRecord]:
    """Yield one RawRecord per data row. The first row must be the header.

    * "utf-8-sig" removes the invisible BOM that Excel puts at the start of CSV files.
    * newline="" lets the csv module handle line breaks inside quoted fields correctly.
    * A row with MORE values than the header is marked as an error (columns would shift).
      A row with FEWER values just has the missing fields as None.
    """
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        try:
            for row in reader:
                location = f"line {reader.line_num}"
                extra = row.pop(None, None)  # DictReader puts surplus values under the key None
                error = f"row has {len(extra)} more value(s) than the header" if extra else None
                yield RawRecord(location, row, error)
        except csv.Error as exc:
            # e.g. a field over 128 KB, or a NUL byte on Python 3.10. After this the reader
            # cannot tell where the next row starts, so the file stops with a clear message.
            # (reader.reader is the low-level reader: its line count is updated even on failure)
            line = reader.reader.line_num
            raise ValueError(f"CSV format error near line {line}: {exc}") from None
