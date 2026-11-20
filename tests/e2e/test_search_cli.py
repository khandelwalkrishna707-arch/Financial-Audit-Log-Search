"""The `find` and `range` commands, run the way a user runs them (issue #2)."""

import sys
import time
from contextlib import closing
from pathlib import Path

import pytest

from audit_search.cli import main
from audit_search.importer import import_file
from audit_search.search.queries import find_by_date_range, find_by_id
from audit_search.storage.database import connect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import generate_synthetic_data  # noqa: E402


@pytest.fixture
def db(tmp_path, fixtures_dir, capsys):
    """A database file containing tests/fixtures/valid.csv."""
    path = tmp_path / "audit.db"
    assert main(["import", "--file", str(fixtures_dir / "valid.csv"), "--db", str(path)]) == 0
    capsys.readouterr()  # forget the import output
    return str(path)


def run(capsys, *args):
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def test_find_exact_id(db, capsys):
    code, out, _ = run(capsys, "find", "--id", "TX-1002", "--db", db)
    assert code == 0
    assert "2026-03-14T09:30:00Z\tTX-1002\tWITHDRAWAL\t1000.50\tAC-2\tu2" in out
    assert out.strip().endswith("1 result")


def test_find_prefix(db, capsys):
    code, out, _ = run(capsys, "find", "--id", "TX-100", "--prefix", "--db", db)
    assert code == 0
    assert out.strip().endswith("4 results")


def test_missing_values_are_shown_as_a_dash(db, capsys):
    _, out, _ = run(capsys, "find", "--id", "TX-1004", "--db", db)
    assert "2026-03-15T00:00:00Z\tTX-1004\tDEPOSIT\t-\tAC-4\tu4" in out


def test_range_includes_whole_end_day(db, capsys):
    code, out, _ = run(capsys, "range", "--from", "14/03/2026", "--to", "2026-03-14", "--db", db)
    assert code == 0
    assert "TX-1003" in out  # stored at 23:59:59 on the end day
    assert "TX-1004" not in out  # next day
    assert out.strip().endswith("3 results")


def test_no_results(db, capsys):
    assert run(capsys, "find", "--id", "NOPE", "--db", db)[:2] == (0, "No results.\n")


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["find", "--id", " "], "must not be empty"),
        (["range", "--from", "2026-03-15", "--to", "2026-03-14"], "is after end date"),
        (["range", "--from", "2026-03-01", "--to", "31/02/2026"], "bad end date"),
    ],
)
def test_bad_input_gives_error_without_traceback(db, capsys, args, message):
    code, _, err = run(capsys, *args, "--db", db)
    assert code == 1
    assert err.startswith("error: ") and message in err


def test_missing_database_is_reported_not_created(tmp_path, capsys):
    path = tmp_path / "nothing.db"
    code, _, err = run(capsys, "find", "--id", "TX-1", "--db", str(path))
    assert code == 1
    assert "database not found" in err
    assert not path.exists()


def test_queries_under_50ms_on_10k_records(tmp_path):
    """PRD target: indexed queries return in under 50 ms on a 10,000-record database."""
    source = tmp_path / "audit_10k.csv"
    generate_synthetic_data.write(generate_synthetic_data.make_rows(10_000, seed=11), source, "csv")
    with closing(connect(tmp_path / "audit.db")) as conn:
        import_file(conn, source)

        timings = []
        for number in range(1, 10_000, 100):
            started = time.perf_counter()
            find_by_id(conn, f"TX-{number:06d}")
            timings.append(time.perf_counter() - started)
        for month in range(1, 13):
            started = time.perf_counter()
            find_by_date_range(conn, f"2026-{month:02d}-01", f"2026-{month:02d}-28")
            timings.append(time.perf_counter() - started)

    assert max(timings) < 0.050, f"slowest query took {max(timings) * 1000:.1f} ms"
