"""Measure the PRD performance targets on synthetic data.

  * import: 10,000 records in under 3.0 seconds
  * search: indexed queries (exact ID, prefix, one-month range) under 50 ms on a
    10,000-record database; a full-year range is also shown, for information

Everything happens in a temporary folder that is deleted afterwards; nothing touches
your own audit.db. Exit code 0 = all targets met, 1 = at least one target missed.

Usage:
    python scripts/benchmark.py                 # 10,000 rows, 100 runs per query
    python scripts/benchmark.py --rows 100000   # see how it scales
"""

from __future__ import annotations

import argparse
import platform
import random
import sqlite3
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

import generate_synthetic_data  # lives next to this script

from audit_search.importer import import_file
from audit_search.search.queries import find_by_date_range, find_by_id, find_by_prefix
from audit_search.storage.database import connect, count_events

IMPORT_TARGET_SECONDS = 3.0
QUERY_TARGET_MS = 50.0


def time_call(func: Callable[[], object], repeat: int) -> list[float]:
    """Run `func` `repeat` times and return each duration in milliseconds."""
    durations = []
    for _ in range(repeat):
        started = time.perf_counter()
        func()
        durations.append((time.perf_counter() - started) * 1000)
    return durations


def verdict(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def run(rows: int, repeat: int, seed: int) -> bool:
    print(f"Benchmark: {rows:,} rows, {repeat} runs per query, seed {seed}")
    print(f"Python {platform.python_version()}, SQLite {sqlite3.sqlite_version}, "
          f"{platform.system()} {platform.machine()}\n")

    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / "audit.csv"
        generate_synthetic_data.write(generate_synthetic_data.make_rows(rows, seed), source, "csv")

        with closing(connect(Path(folder) / "audit.db")) as conn:
            started = time.perf_counter()
            summary = import_file(conn, source)
            import_seconds = time.perf_counter() - started
            stored = count_events(conn)

            import_ok = rows > 10_000 or import_seconds < IMPORT_TARGET_SECONDS
            target = f"< {IMPORT_TARGET_SECONDS} s" if rows <= 10_000 else "(target is for 10k)"
            print(f"{'import':<18}{import_seconds:>9.3f} s   {stored:,} stored, "
                  f"{summary.rejected} rejected   target {target}  {verdict(import_ok)}\n")

            rng = random.Random(seed)
            ids = [row[0] for row in conn.execute("SELECT transaction_id FROM audit_events")]
            months = [(f"2026-{m:02d}-01", f"2026-{m:02d}-28") for m in range(1, 13)]

            # (name, query, checked against the target?)
            # The full-year range returns EVERY row, so its time is mostly Python building
            # thousands of objects, not the indexed lookup the target is about. It is shown
            # for information only, so a slow machine can't make the benchmark fail randomly.
            queries: list[tuple[str, Callable[[], list], bool]] = [
                ("exact ID", lambda: find_by_id(conn, rng.choice(ids)), True),
                ("prefix (7 chars)", lambda: find_by_prefix(conn, rng.choice(ids)[:7]), True),
                ("1-month range", lambda: find_by_date_range(conn, *rng.choice(months)), True),
                ("full-year range",
                 lambda: find_by_date_range(conn, "2026-01-01", "2026-12-31"), False),
            ]

            print(f"{'query':<18}{'avg ms':>9}{'p95 ms':>9}{'max ms':>9}{'rows':>8}   target")
            queries_ok = True
            for name, query, checked in queries:
                durations = sorted(time_call(query, repeat))
                p95 = durations[min(len(durations) - 1, int(len(durations) * 0.95))]
                result_rows = len(query())
                if checked:
                    ok = durations[-1] < QUERY_TARGET_MS
                    queries_ok &= ok
                    target = f"max < {QUERY_TARGET_MS:g} ms  {verdict(ok)}"
                else:
                    target = "info only (returns all rows)"
                print(f"{name:<18}{statistics.mean(durations):>9.3f}{p95:>9.3f}"
                      f"{durations[-1]:>9.3f}{result_rows:>8,}   {target}")

    all_ok = import_ok and queries_ok
    print(f"\nResult: {'all targets met' if all_ok else 'TARGET MISSED'}")
    return all_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure import time and query latency.")
    parser.add_argument("--rows", type=int, default=10_000, help="rows to generate (default 10000)")
    parser.add_argument("--repeat", type=int, default=100, help="runs per query (default 100)")
    parser.add_argument("--seed", type=int, default=42, help="random seed (default 42)")
    args = parser.parse_args(argv)
    if args.rows < 1 or args.repeat < 1:
        parser.error("--rows and --repeat must be at least 1")
    return 0 if run(args.rows, args.repeat, args.seed) else 1


if __name__ == "__main__":
    sys.exit(main())
