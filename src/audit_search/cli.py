"""Command-line entry point: `audit-search <command> [options]`.

Commands
  import  -> load a CSV/JSON/JSONL audit log into the database
  find    -> look up a transaction ID (exact or --prefix)
  range   -> list events between two dates (both included)
  menu    -> interactive terminal menu
  web     -> local Flask dashboard on 127.0.0.1 (needs: pip install ".[web]")
  --export on find/range writes the results to CSV; --account/--user/--action and
  --min-amount/--max-amount narrow the results.

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
from audit_search.export.csv_writer import ExportError, write_csv
from audit_search.export.formatter import format_table
from audit_search.export.style import paint, use_color
from audit_search.importer import import_file
from audit_search.models import ImportSummary
from audit_search.search.filters import Filters
from audit_search.search.service import search
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

    # ---- search -----------------------------------------------------------------------
    p_find = commands.add_parser("find", parents=[common], help="find events by transaction ID")
    p_find.add_argument("--id", required=True, dest="transaction_id", help="transaction ID")
    p_find.add_argument("--prefix", action="store_true", help="match IDs that start with --id")
    _add_result_options(p_find)
    p_find.set_defaults(handler=cmd_find)

    p_range = commands.add_parser("range", parents=[common], help="list events in a date range")
    p_range.add_argument("--from", required=True, dest="start", help="start date (inclusive)")
    p_range.add_argument("--to", required=True, dest="end", help="end date (inclusive)")
    _add_result_options(p_range)
    p_range.set_defaults(handler=cmd_range)

    # ---- interactive front ends -------------------------------------------------------
    p_menu = commands.add_parser("menu", parents=[common], help="interactive terminal menu")
    p_menu.set_defaults(handler=cmd_menu)

    p_web = commands.add_parser(
        "web", parents=[common], help="local web dashboard on 127.0.0.1 (needs Flask)"
    )
    p_web.add_argument("--port", type=int, default=5000, help="port (default: %(default)s)")
    p_web.set_defaults(handler=cmd_web)

    return parser


def _add_result_options(command: argparse.ArgumentParser) -> None:
    command.add_argument("--export", type=Path, help="also write the results to this CSV file")
    command.add_argument("--account", help="only events for this account ID")
    command.add_argument("--user", help="only events by this user ID")
    command.add_argument("--action", help="only this action type, e.g. DEPOSIT")
    command.add_argument("--min-amount", help="only amounts >= this, e.g. 100.00")
    command.add_argument("--max-amount", help="only amounts <= this")


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
    color = use_color()

    def count(label: str, value: int, style: str) -> None:
        shown = paint(str(value), "bold", style, enabled=color and value > 0)
        print(f"  {label:<19}: {shown}")

    print(paint(f"Imported {summary.source_file} in {seconds:.2f}s", "bold", enabled=color))
    print(f"  rows read          : {summary.read}")
    count("inserted", summary.inserted, "green")
    count("duplicates skipped", summary.skipped_duplicates, "yellow")
    count("duplicates updated", summary.updated, "yellow")
    count("rejected", summary.rejected, "red")
    if summary.rejections:
        print(paint(f"Rejected rows (first {min(REJECTIONS_SHOWN, summary.rejected)}):",
                    "red", enabled=color))
        for rejection in summary.rejections[:REJECTIONS_SHOWN]:
            print(f"  {paint(rejection.location, 'dim', enabled=color)}: {rejection.reason}")
        if summary.rejected > REJECTIONS_SHOWN:
            print(f"  ... and {summary.rejected - REJECTIONS_SHOWN} more")


def cmd_find(args: argparse.Namespace) -> int:
    return _run_search(args, transaction_id=args.transaction_id, prefix=args.prefix)


def cmd_range(args: argparse.Namespace) -> int:
    return _run_search(args, start=args.start, end=args.end)


def _run_search(args: argparse.Namespace, **criteria) -> int:
    if not Path(args.db).is_file():
        # sqlite3 would silently create an empty database and report "No results."
        print(f"error: database not found: {args.db} (run 'audit-search import' first)",
              file=sys.stderr)
        return 1
    try:
        filters = Filters.from_text(args.account, args.user, args.action,
                                    args.min_amount, args.max_amount)
        with closing(connect(args.db)) as conn:
            results = search(conn, filters=filters, **criteria)
    except (ValueError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(format_table(results, color=use_color()))
    if args.export:
        try:
            written = write_csv(results, args.export)
        except ExportError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        message = f"Exported {written} row{'s' if written != 1 else ''} to {args.export}"
        print(paint(message, "green", enabled=use_color()))
    return 0


def cmd_menu(args: argparse.Namespace) -> int:
    from audit_search.menu import run_menu

    return run_menu(args.db)


def cmd_web(args: argparse.Namespace) -> int:
    try:
        from audit_search.web import create_app
    except ImportError:
        print('error: the web UI needs Flask. Install it with: pip install ".[web]"',
              file=sys.stderr)
        return 1
    from audit_search.web import HOST

    app = create_app(args.db)
    print(f"Audit search dashboard on http://{HOST}:{args.port} (Ctrl+C to stop)")
    app.run(host=HOST, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
