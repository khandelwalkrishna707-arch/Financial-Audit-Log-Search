"""Run the real command-line interface, the way a user would."""

import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

import pytest

from audit_search.cli import main
from audit_search.storage.database import connect, count_events

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import generate_synthetic_data  # noqa: E402


def test_import_command_prints_summary(tmp_path, fixtures_dir, capsys):
    db = tmp_path / "audit.db"
    assert main(["import", "--file", str(fixtures_dir / "corrupted.csv"), "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "inserted           : 3" in out
    assert "rejected           : 5" in out
    assert "line 3: missing transaction_id" in out


def test_import_command_reports_errors_without_traceback(tmp_path, capsys):
    db = str(tmp_path / "audit.db")
    assert main(["import", "--file", str(tmp_path / "missing.csv"), "--db", db]) == 1
    assert "error: file not found" in capsys.readouterr().err

    (tmp_path / "log.xml").write_text("<x/>")
    assert main(["import", "--file", str(tmp_path / "log.xml"), "--db", db]) == 1
    assert "unsupported file type" in capsys.readouterr().err


def test_non_utf8_file_gives_a_helpful_message(tmp_path, capsys):
    path = tmp_path / "latin1.csv"
    path.write_bytes("transaction_id,event_date\nTX-1,café\n".encode("latin-1"))
    assert main(["import", "--file", str(path), "--db", str(tmp_path / "a.db")]) == 1
    assert "is not UTF-8 text" in capsys.readouterr().err


def test_long_rejection_list_is_truncated(tmp_path, capsys):
    path = tmp_path / "bad.csv"
    path.write_text("transaction_id,event_date\n" + "X,bad\n" * 25)
    main(["import", "--file", str(path), "--db", str(tmp_path / "a.db")])
    assert "... and 5 more" in capsys.readouterr().out


def test_invalid_duplicate_policy_is_refused(fixtures_dir):
    with pytest.raises(SystemExit):
        main(["import", "--file", str(fixtures_dir / "valid.csv"), "--on-duplicate", "merge"])


def test_python_dash_m_entry_point(tmp_path, fixtures_dir):
    result = subprocess.run(
        [sys.executable, "-m", "audit_search", "import",
         "--file", str(fixtures_dir / "valid.csv"), "--db", str(tmp_path / "a.db")],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "inserted           : 4" in result.stdout


def test_import_10k_rows_under_3_seconds(tmp_path):
    """PRD target: 10,000 records ingested in under 3.0 seconds."""
    source = tmp_path / "audit_10k.csv"
    generate_synthetic_data.write(generate_synthetic_data.make_rows(10_000, seed=7), source, "csv")
    db = tmp_path / "audit.db"

    started = time.perf_counter()
    assert main(["import", "--file", str(source), "--db", str(db)]) == 0
    elapsed = time.perf_counter() - started

    assert elapsed < 3.0, f"import took {elapsed:.2f}s"
    with closing(connect(db)) as conn:
        assert count_events(conn) > 9_000


@pytest.mark.parametrize("fmt", ["json", "jsonl"])
def test_generated_json_formats_import(tmp_path, fmt):
    source = tmp_path / f"audit.{fmt}"
    generate_synthetic_data.write(generate_synthetic_data.make_rows(300, seed=9), source, fmt)
    assert main(["import", "--file", str(source), "--db", str(tmp_path / "a.db")]) == 0
