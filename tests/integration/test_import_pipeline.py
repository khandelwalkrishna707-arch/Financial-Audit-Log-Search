"""Whole import path: file -> parser -> validator -> normalizer -> SQLite."""

import pytest

from audit_search.importer import import_file
from audit_search.storage.database import count_events


def stored(conn):
    return {
        row["transaction_id"]: dict(row)
        for row in conn.execute("SELECT * FROM audit_events ORDER BY id")
    }


def test_valid_csv_is_fully_normalized(conn, fixtures_dir):
    summary = import_file(conn, fixtures_dir / "valid.csv")
    assert (summary.read, summary.inserted, summary.rejected) == (4, 4, 0)

    rows = stored(conn)
    assert rows["TX-1001"]["event_date"] == "2026-03-14T09:30:00Z"
    assert rows["TX-1002"]["event_date"] == "2026-03-14T09:30:00Z"  # +05:30 -> UTC
    assert rows["TX-1003"]["event_date"] == "2026-03-14T23:59:59Z"  # DD/MM/YYYY
    assert rows["TX-1004"]["event_date"] == "2026-03-15T00:00:00Z"
    assert [r["amount_cents"] for r in rows.values()] == [125000, 100050, 10, None]
    assert [r["action_type"] for r in rows.values()] == [
        "DEPOSIT", "WITHDRAWAL", "LOAN_REPAYMENT", "DEPOSIT",
    ]
    assert rows["TX-1001"]["source_file"] == "valid.csv"


def test_corrupted_csv_rejects_bad_rows_and_keeps_good_ones(conn, fixtures_dir):
    summary = import_file(conn, fixtures_dir / "corrupted.csv")
    assert summary.inserted == 3
    assert summary.rejected == 5
    reasons = {r.location: r.reason for r in summary.rejections}
    assert reasons["line 3"] == "missing transaction_id"
    assert reasons["line 4"] == "missing event_date"
    assert reasons["line 5"].startswith("bad event_date")
    assert reasons["line 6"].startswith("bad amount")
    assert "more value" in reasons["line 7"]
    assert set(stored(conn)) == {"TX-2001", "TX-2007", "TX-2008"}


def test_json_with_aliases_and_fineract_shapes(conn, fixtures_dir):
    summary = import_file(conn, fixtures_dir / "valid.json")
    assert (summary.inserted, summary.rejected) == (3, 0)
    rows = stored(conn)
    assert rows["TX-3001"]["amount_cents"] == 9999
    assert rows["TX-3002"]["event_date"] == "2026-02-02T00:00:00Z"
    assert rows["TX-3002"]["action_type"] == "WITHDRAWAL"
    assert rows["3003"]["event_date"] == "2026-02-02T02:40:00Z"  # epoch seconds
    assert rows["3003"]["amount_cents"] == 30


def test_fineract_wrapped_audit_json(conn, fixtures_dir):
    summary = import_file(conn, fixtures_dir / "wrapped.json")
    assert summary.inserted == 2
    row = stored(conn)["42"]
    assert (row["action_type"], row["user_id"]) == ("APPROVE", "admin")


def test_jsonl_with_broken_lines(conn, fixtures_dir):
    summary = import_file(conn, fixtures_dir / "corrupted.jsonl")
    assert (summary.read, summary.inserted, summary.rejected) == (4, 2, 2)


def test_reimport_with_skip_counts_duplicates(conn, fixtures_dir):
    import_file(conn, fixtures_dir / "valid.csv")
    again = import_file(conn, fixtures_dir / "valid.csv", policy="skip")
    assert (again.inserted, again.skipped_duplicates, again.duplicates) == (0, 4, 4)
    assert count_events(conn) == 4


def test_reimport_with_update_overwrites(conn, fixtures_dir, tmp_path):
    import_file(conn, fixtures_dir / "valid.csv")
    changed = tmp_path / "changed.csv"
    changed.write_text(
        "transaction_id,event_date,action_type,amount\n"
        "TX-1001,14/03/2026 09:30:00,DEPOSIT,1300.00\n"  # same event, other date format
    )
    summary = import_file(conn, changed, policy="update")
    assert (summary.inserted, summary.updated) == (0, 1)
    row = stored(conn)["TX-1001"]
    assert (row["amount_cents"], row["source_file"]) == (130000, "changed.csv")


def test_small_batches_give_same_result(conn, fixtures_dir):
    summary = import_file(conn, fixtures_dir / "corrupted.csv", batch_size=1)
    assert (summary.inserted, summary.rejected) == (3, 5)


def test_rejection_details_are_capped_but_all_counted(conn, tmp_path, monkeypatch):
    monkeypatch.setattr("audit_search.models.MAX_REJECTIONS_KEPT", 2)
    path = tmp_path / "bad.csv"
    path.write_text("transaction_id,event_date\n" + "X,not-a-date\n" * 5)
    summary = import_file(conn, path)
    assert summary.rejected == 5
    assert len(summary.rejections) == 2


def test_broken_json_array_keeps_records_before_the_error(conn, fixtures_dir):
    with pytest.raises(ValueError, match="record 2"):
        import_file(conn, fixtures_dir / "broken_array.json", batch_size=1)
    assert set(stored(conn)) == {"TX-5001"}


def test_extreme_values_are_rejected_not_crashing(conn, tmp_path):
    """PRD: malformed rows must never crash the import."""
    path = tmp_path / "extreme.json"
    path.write_text(
        '[{"transaction_id": "TX-1", "event_date": [100000000000000000000, 1, 1]},'
        ' {"transaction_id": "TX-2", "event_date": 0},'
        ' {"transaction_id": "TX-3", "event_date": "2026-01-01", "amount": "1e30"},'
        ' {"transaction_id": "TX-4", "event_date": 20260314, "amount": 1e2}]'
    )
    summary = import_file(conn, path)
    assert (summary.inserted, summary.rejected) == (1, 3)
    row = stored(conn)["TX-4"]
    assert (row["event_date"], row["amount_cents"]) == ("2026-03-14T00:00:00Z", 10000)


def test_missing_file(conn, tmp_path):
    with pytest.raises(FileNotFoundError):
        import_file(conn, tmp_path / "nope.csv")
