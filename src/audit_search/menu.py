"""Interactive terminal menu. TODO (week 2): implement `run_menu`.

It should loop until the user picks Quit:

    1) Import a file
    2) Find by transaction ID
    3) Find by date range
    4) Export last results to CSV
    5) Quit

Reuse the same functions the CLI uses (importer.import_file, search.queries.*,
export.*). The menu must not contain its own SQL or parsing logic.
Bad input (e.g. "abc" as a menu choice, an invalid date) should print a message and
show the menu again, never crash.
"""

from __future__ import annotations


def run_menu(db_path: str) -> int:
    """Run the menu loop. Return 0 when the user quits."""
    raise NotImplementedError("TODO(week 2)")
