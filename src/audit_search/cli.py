"""Command-line entry point: `audit-search <command> [options]`.

Commands
  import  -> DONE: load a CSV/JSON/JSONL audit log into the database
  find    -> TODO (week 2): look up a transaction ID (exact or --prefix)
  range   -> TODO (week 2): list events between two dates
  menu    -> TODO (week 2): interactive terminal menu

The CLI only reads arguments, calls the service functions and prints results.
It holds no business logic of its own, so the menu and the web UI can reuse the same services.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

from audit_search import __version__
from audit_search.config import DEFAULT_DB_PATH, DEFAULT_DUPLICATE_POLICY, DUPLICATE_POLICIES
from audit_search.importer import import_file
from audit_search.models import ImportSummary
from audit_search.storage.database import connect

REJECTIONS_SHOWN = 20


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--db", default=DEFAULT_DB_PATH, help=f"SQLite database file (default: {DEFAULT_DB_PATH})"
    )

    parser = argparse.ArgumentParser(
        prog="audit-search",
        description="Index financial audit logs locally and search them by transaction ID or date.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    # ---- import (done) -----------------------------------------------------------------
    p_import = commands.add_parser(
        "import", parents=[common], help="import a CSV, JSON or JSONL audit log"
    )
    p_import.add_argument("--file", required=True, type=Path, help="audit log file to import")
    p_import.add_argument(
        "--on-duplicate",
        choices=DUPLICATE_POLICIES,
        default=DEFAULT_DUPLICATE_POLICY,
        help="what to do with events that are already stored (default: %(default)s)",
    )
    p_import.set_defaults(handler=cmd_import)

    # ---- search side: TODO week 2 (see docs/remaining_work.md) -------------------------
    p_find = commands.add_parser("find", parents=[common], help="find events by transaction ID")
    p_find.add_argument("--id", required=True, dest="transaction_id", help="transaction ID")
    p_find.add_argument("--prefix", action="store_true", help="match IDs that start with --id")
    p_find.add_argument("--export", type=Path, help="also write the results to this CSV file")
    p_find.set_defaults(handler=_not_built_yet)

    p_range = commands.add_parser("range", parents=[common], help="list events in a date range")
    p_range.add_argument("--from", required=True, dest="start", help="start date (inclusive)")
    p_range.add_argument("--to", required=True, dest="end", help="end date (inclusive)")
    p_range.add_argument("--export", type=Path, help="also write the results to this CSV file")
    p_range.set_defaults(handler=_not_built_yet)

    p_menu = commands.add_parser("menu", parents=[common], help="interactive terminal menu")
    p_menu.set_defaults(handler=_not_built_yet)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


# --------------------------------------------------------------------------- handlers


def cmd_import(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    try:
        with closing(connect(args.db)) as conn:
            summary = import_file(conn, args.file, policy=args.on_duplicate)
    except UnicodeDecodeError:
        print(
            f"error: {args.file} is not UTF-8 text. Re-save it as UTF-8 "
            "(in Excel: 'CSV UTF-8') and import it again.",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print_import_summary(summary, time.perf_counter() - started)
    return 0


def print_import_summary(summary: ImportSummary, seconds: float) -> None:
    print(f"Imported {summary.source_file} in {seconds:.2f}s")
    print(f"  rows read          : {summary.read}")
    print(f"  inserted           : {summary.inserted}")
    print(f"  duplicates skipped : {summary.skipped_duplicates}")
    print(f"  duplicates updated : {summary.updated}")
    print(f"  rejected           : {summary.rejected}")
    if summary.rejections:
        print(f"Rejected rows (first {min(REJECTIONS_SHOWN, summary.rejected)}):")
        for rejection in summary.rejections[:REJECTIONS_SHOWN]:
            print(f"  {rejection.location}: {rejection.reason}")
        if summary.rejected > REJECTIONS_SHOWN:
            print(f"  ... and {summary.rejected - REJECTIONS_SHOWN} more")


def _not_built_yet(args: argparse.Namespace) -> int:
    print(
        f"'{args.command}' is not built yet - see docs/remaining_work.md",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
