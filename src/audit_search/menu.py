"""Interactive terminal menu (`audit-search menu`).

    1) Import a file
    2) Find by transaction ID
    3) Find by date range
    4) Export last results to CSV
    5) Quit

It reuses the same service functions as the CLI (importer.import_file, search.service.search,
export.*) and holds no SQL or parsing logic of its own. Bad input prints a message and shows
the menu again; it never crashes. `input_func` and `print_func` can be replaced in tests.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

from audit_search.config import DEFAULT_DUPLICATE_POLICY
from audit_search.export.csv_writer import ExportError, write_csv
from audit_search.export.formatter import format_table
from audit_search.importer import import_file
from audit_search.models import Transaction
from audit_search.search.service import search
from audit_search.storage.database import connect

MENU = """
Audit log search
  1) Import a file
  2) Find by transaction ID
  3) Find by date range
  4) Export last results to CSV
  5) Quit"""


def run_menu(
    db_path: str,
    input_func: Callable[[str], str] | None = None,
    print_func: Callable[..., None] | None = None,
) -> int:
    """Run the menu loop. Return 0 when the user quits (or input ends)."""
    input_func = input_func or input
    print_func = print_func or print
    last_results: list[Transaction] | None = None

    def ask(prompt: str) -> str:
        return input_func(prompt).strip()

    while True:
        print_func(MENU)
        try:
            choice = ask("Choose 1-5: ")
        except (EOFError, KeyboardInterrupt):
            print_func("")
            return 0
        try:
            if choice == "1":
                path = Path(ask("File to import: "))
                with closing(connect(db_path)) as conn:
                    summary = import_file(conn, path, policy=DEFAULT_DUPLICATE_POLICY)
                print_func(
                    f"Imported {summary.source_file}: {summary.inserted} inserted, "
                    f"{summary.duplicates} duplicates, {summary.rejected} rejected"
                )
                for rejection in summary.rejections[:10]:
                    print_func(f"  {rejection.location}: {rejection.reason}")
            elif choice in ("2", "3"):
                if not Path(db_path).is_file():
                    print_func(f"No database at {db_path} yet. Import a file first (option 1).")
                    continue
                if choice == "2":
                    tx_id = ask("Transaction ID (end with * for a prefix search): ")
                    prefix = tx_id.endswith("*")
                    criteria = {"transaction_id": tx_id.rstrip("*"), "prefix": prefix}
                else:
                    criteria = {"start": ask("From date: "), "end": ask("To date: ")}
                with closing(connect(db_path)) as conn:
                    last_results = search(conn, **criteria)
                print_func(format_table(last_results))
            elif choice == "4":
                if last_results is None:
                    print_func("Nothing to export yet. Run a search first (option 2 or 3).")
                    continue
                target = ask("Export to CSV file: ")
                if not target:
                    print_func("No file name given.")
                    continue
                written = write_csv(last_results, target)
                print_func(f"Exported {written} rows to {target}")
            elif choice == "5":
                return 0
            else:
                print_func(f"Unknown choice {choice!r}. Type a number from 1 to 5.")
        except (EOFError, KeyboardInterrupt):
            print_func("")
            return 0
        except UnicodeDecodeError:
            print_func("Error: that file is not UTF-8 text. Re-save it as UTF-8 and try again.")
        except (OSError, ValueError, sqlite3.Error, ExportError) as exc:
            print_func(f"Error: {exc}")
