"""CSV export and terminal table."""

import csv
import io
from contextlib import closing

import pytest

from audit_search.export.csv_writer import (
    EXPORT_HEADERS,
    ExportError,
    write_csv,
    write_rows,
)
from audit_search.export.formatter import format_table, result_count
from audit_search.importer import import_file
from audit_search.models import Transaction
from audit_search.search.queries import find_by_date_range
from audit_search.storage.database import connect

TX = Transaction("TX-1", "2026-03-14T09:30:00Z", "AC-1", "DEPOSIT", 1250, "u1", "a.csv")


def test_header_written_even_with_no_rows(tmp_path):
    path = tmp_path / "out.csv"
    assert write_csv([], path) == 0
    assert path.read_text(encoding="utf-8") == ",".join(EXPORT_HEADERS) + "\n"


def test_amount_and_missing_values(tmp_path):
    path = tmp_path / "out.csv"
    empty = Transaction("TX-2", "2026-03-15T00:00:00Z")
    assert write_csv([TX, empty], path) == 2
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert rows[0]["amount"] == "12.50"
    assert rows[1] == {**dict.fromkeys(EXPORT_HEADERS, ""),
                       "transaction_id": "TX-2", "event_date": "2026-03-15T00:00:00Z"}


def test_negative_amount_is_exported_exactly():
    buffer = io.StringIO()
    write_rows([Transaction("TX-3", "2026-01-01T00:00:00Z", amount_cents=-5)], buffer)
    assert buffer.getvalue().splitlines()[1].split(",")[4] == "-0.05"


def test_round_trip_keeps_every_value_including_commas(tmp_path, fixtures_dir):
    """PRD data-integrity target: what goes in comes back out unchanged."""
    db = tmp_path / "a.db"
    with closing(connect(db)) as conn:
        import_file(conn, fixtures_dir / "valid.csv")
        import_file(conn, fixtures_dir / "corrupted.csv")
        stored = find_by_date_range(conn, "2000-01-01", "2100-01-01")
    out = tmp_path / "out.csv"
    write_csv(stored, out)
    with out.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames) == EXPORT_HEADERS
        rows = list(reader)
    assert len(rows) == len(stored)
    for tx, row in zip(stored, rows, strict=True):
        assert row["transaction_id"] == tx.transaction_id
        assert row["event_date"] == tx.event_date
        assert row["account_id"] == (tx.account_id or "")
        assert row["action_type"] == tx.action_type
        assert row["user_id"] == (tx.user_id or "")
    assert any(row["account_id"] == "Smith, J" for row in rows)
    by_id = {row["transaction_id"]: row for row in rows}
    assert by_id["TX-1002"]["amount"] == "1000.50"
    assert by_id["TX-1003"]["amount"] == "0.10"
    assert by_id["TX-1004"]["amount"] == ""


def test_write_error_is_clear(tmp_path):
    with pytest.raises(ExportError, match="could not write"):
        write_csv([TX], tmp_path / "missing-folder" / "out.csv")


def test_table_is_aligned():
    other = Transaction("TX-10000", "2026-03-15T00:00:00Z", None, "WITHDRAWAL", 100050, None)
    lines = format_table([TX, other]).splitlines()
    assert lines[0].split() == ["transaction_id", "event_date", "action_type", "amount",
                                "account_id", "user_id"]
    assert set(lines[1].replace(" ", "")) == {"-"}
    # amounts are right-aligned: the decimal points line up
    assert lines[2].index("12.50") + 5 == lines[3].index("1000.50") + 7
    assert lines[3].split()[-1] == "-"  # missing user_id
    assert lines[-1] == "2 results"


def test_empty_table_and_counts():
    assert format_table([]) == "No results."
    assert result_count(1) == "1 result"
    assert result_count(0) == "0 results"


def test_colored_table_keeps_layout():
    neg = Transaction("TX-9", "2026-03-16T00:00:00Z", "AC-9", "FEE_CHARGE", -500, None)
    plain = format_table([TX, neg])
    colored = format_table([TX, neg], color=True)
    assert "\033[" in colored
    assert strip_ansi(colored) == plain
    assert "\033[31m" in colored  # negative amount / fee in red
    assert format_table([], color=True) == "\033[33mNo results.\033[0m"


def strip_ansi(text):
    import re
    return re.sub(r"\033\[[0-9;]*m", "", text)


def test_use_color(monkeypatch):
    from audit_search.export.style import paint, use_color

    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    assert use_color(Tty())
    assert not use_color(io.StringIO())
    monkeypatch.setenv("NO_COLOR", "1")
    assert not use_color(Tty())
    assert paint("x", "nope") == "x"
    assert paint("x", "bold", enabled=False) == "x"
