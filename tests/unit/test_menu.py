"""The interactive menu, driven with fake input/print functions."""

import csv

from audit_search.menu import run_menu


def drive(db, answers):
    feed = iter(answers)
    printed = []

    def fake_input(prompt):
        try:
            return next(feed)
        except StopIteration:
            raise EOFError from None

    code = run_menu(str(db), input_func=fake_input,
                    print_func=lambda *a: printed.append(" ".join(map(str, a))))
    return code, "\n".join(printed)


def test_full_session(tmp_path, fixtures_dir):
    db = tmp_path / "a.db"
    out_csv = tmp_path / "out.csv"
    code, out = drive(db, [
        "1", str(fixtures_dir / "corrupted.csv"),
        "2", "TX-2001",
        "2", "TX-200*",
        "3", "2026-01-01", "2026-01-31",
        "4", str(out_csv),
        "5",
    ])
    assert code == 0
    assert "3 inserted" in out and "5 rejected" in out
    assert "line 3: missing transaction_id" in out
    assert "1 result" in out
    rows = list(csv.DictReader(out_csv.open(encoding="utf-8")))
    assert len(rows) == 3
    assert "Exported 3 rows" in out


def test_bad_input_never_crashes(tmp_path, fixtures_dir):
    db = tmp_path / "a.db"
    code, out = drive(db, [
        "abc",
        "2", "TX-1",                       # no database yet
        "4",                               # nothing searched yet
        "1", str(tmp_path / "missing.csv"),
        "1", str(fixtures_dir / "valid.csv"),
        "3", "2026-03-15", "2026-03-01",   # start after end
        "3", "nonsense", "2026-03-01",
        "2", "TX-1001",
        "4", "",                           # no file name
        "4", str(tmp_path / "no-dir" / "x.csv"),
    ])  # input then ends -> EOF quits cleanly
    assert code == 0
    assert "Unknown choice 'abc'" in out
    assert "Import a file first" in out
    assert "Run a search first" in out
    assert "file not found" in out
    assert "after end date" in out
    assert "bad start date" in out
    assert "No file name given" in out
    assert "could not write" in out


def test_non_utf8_file(tmp_path):
    path = tmp_path / "latin1.csv"
    path.write_bytes("transaction_id,event_date\nTX-1,café\n".encode("latin-1"))
    _, out = drive(tmp_path / "a.db", ["1", str(path), "5"])
    assert "not UTF-8" in out


def test_ctrl_c_quits(tmp_path):
    def interrupt(prompt):
        raise KeyboardInterrupt
    assert run_menu(str(tmp_path / "a.db"), input_func=interrupt, print_func=lambda *a: None) == 0


def test_ctrl_c_inside_a_step_quits(tmp_path):
    answers = iter(["1"])

    def fake_input(prompt):
        value = next(answers, None)
        if value is None:
            raise KeyboardInterrupt
        return value
    assert run_menu(str(tmp_path / "a.db"), input_func=fake_input,
                    print_func=lambda *a: None) == 0
