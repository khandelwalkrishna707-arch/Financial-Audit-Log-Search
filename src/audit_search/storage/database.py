"""Open the SQLite database, create the schema, and write rows in batches.

This is the ONLY module that knows how to connect to the database. If the project ever
moves to PostgreSQL, this file (and the SQL in storage/ and search/) is what changes.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from collections.abc import Iterable
from importlib import resources
from pathlib import Path

from audit_search.config import DUPLICATE_POLICIES
from audit_search.models import Transaction
from audit_search.storage.duplicates import Outcome, store


def connect(db_path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open (or create) the database file and make sure the table and indexes exist.

    isolation_level=None means sqlite3 never starts transactions by itself;
    we start and end them explicitly in `insert_batch`, so batching is easy to see.
    """
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row  # rows can be read by column name: row["event_date"]
    init_schema(conn)
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    schema = resources.files("audit_search.storage").joinpath("schema.sql").read_text("utf-8")
    conn.executescript(schema)  # fixed SQL from our own file; contains no user input


def insert_batch(
    conn: sqlite3.Connection, transactions: Iterable[Transaction], policy: str
) -> Counter[Outcome]:
    """Write a batch inside ONE transaction: either the whole batch is saved, or none of it.

    One transaction per 1,000 rows is much faster than one per row, because SQLite only
    has to flush to disk once per batch.
    """
    if policy not in DUPLICATE_POLICIES:
        raise ValueError(f"unknown duplicate policy {policy!r}; use one of {DUPLICATE_POLICIES}")

    outcomes: Counter[Outcome] = Counter()
    cursor = conn.cursor()
    cursor.execute("BEGIN")
    try:
        for tx in transactions:
            outcomes[store(cursor, tx, policy)] += 1
    except BaseException:
        if conn.in_transaction:  # SQLite rolls back by itself on some errors (e.g. disk full)
            cursor.execute("ROLLBACK")
        raise
    cursor.execute("COMMIT")
    return outcomes


def count_events(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]


_OVERVIEW_SQL = """
    SELECT COUNT(*) AS events,
           MIN(event_date) AS first_date,
           MAX(event_date) AS last_date,
           COUNT(DISTINCT source_file) AS files
      FROM audit_events
"""


def database_overview(conn: sqlite3.Connection) -> dict[str, object]:
    """How many events are stored, the date span they cover, and how many files they came from."""
    row = conn.execute(_OVERVIEW_SQL).fetchone()
    return {"events": row[0], "first_date": row[1], "last_date": row[2], "files": row[3]}
