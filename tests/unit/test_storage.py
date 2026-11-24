import sqlite3
from contextlib import closing

import pytest

from audit_search.models import Transaction
from audit_search.storage.database import connect, count_events, insert_batch
from audit_search.storage.duplicates import Outcome


def tx(tx_id="TX-1", date="2026-01-01T00:00:00Z", action="DEPOSIT", amount=100, source="a"):
    return Transaction(tx_id, date, "AC-1", action, amount, "u1", source)


def test_schema_has_id_and_date_indexes_and_unique_key(conn):
    indexes = {row["name"] for row in conn.execute("PRAGMA index_list(audit_events)")}
    assert "idx_tx_date" in indexes
    assert "idx_tx_id" in indexes
    assert any(name.startswith("sqlite_autoindex_audit_events") for name in indexes)


def test_connect_is_idempotent(tmp_path):
    db = tmp_path / "audit.db"
    first = connect(db)
    insert_batch(first, [tx()], "skip")
    first.close()
    with closing(connect(db)) as again:  # opening again must not fail or wipe data
        assert count_events(again) == 1


def test_connect_adds_idx_tx_id_to_an_older_database(tmp_path):
    db = tmp_path / "old.db"
    with closing(connect(db)) as first:
        first.execute("DROP INDEX idx_tx_id")  # a database made before issue #4
    with closing(connect(db)) as again:
        indexes = {row["name"] for row in again.execute("PRAGMA index_list(audit_events)")}
        assert "idx_tx_id" in indexes


def test_insert_new_rows(conn):
    outcomes = insert_batch(conn, [tx("TX-1"), tx("TX-2")], "skip")
    assert outcomes[Outcome.INSERTED] == 2
    assert count_events(conn) == 2


def test_skip_policy_keeps_original(conn):
    insert_batch(conn, [tx(amount=100, source="first")], "skip")
    outcomes = insert_batch(conn, [tx(amount=999, source="second")], "skip")
    assert outcomes[Outcome.SKIPPED] == 1
    row = conn.execute("SELECT amount_cents, source_file FROM audit_events").fetchone()
    assert tuple(row) == (100, "first")


def test_update_policy_overwrites_details(conn):
    insert_batch(conn, [tx(amount=100, source="first")], "skip")
    outcomes = insert_batch(conn, [tx(amount=999, source="second")], "update")
    assert outcomes[Outcome.UPDATED] == 1
    assert count_events(conn) == 1
    row = conn.execute("SELECT amount_cents, source_file FROM audit_events").fetchone()
    assert tuple(row) == (999, "second")


def test_duplicates_inside_one_batch_are_detected(conn):
    outcomes = insert_batch(conn, [tx(), tx(), tx()], "skip")
    assert outcomes[Outcome.INSERTED] == 1
    assert outcomes[Outcome.SKIPPED] == 2


def test_same_transaction_different_event_is_not_a_duplicate(conn):
    rows = [
        tx(action="DISBURSEMENT"),
        tx(action="REPAYMENT"),  # same ID and time, different action
        tx(date="2026-01-02T00:00:00Z"),  # same ID, different time
    ]
    assert insert_batch(conn, rows, "skip")[Outcome.INSERTED] == 3


def test_unknown_policy_is_refused(conn):
    with pytest.raises(ValueError, match="unknown duplicate policy"):
        insert_batch(conn, [tx()], "merge")


def test_failed_batch_is_rolled_back(conn):
    bad = Transaction(None, "2026-01-01T00:00:00Z")  # violates NOT NULL
    with pytest.raises(sqlite3.IntegrityError):
        insert_batch(conn, [tx("TX-OK"), bad], "skip")
    assert count_events(conn) == 0  # TX-OK was rolled back too: all or nothing


def test_sql_injection_text_is_stored_as_plain_data(conn):
    evil = "TX-1'; DROP TABLE audit_events; --"
    insert_batch(conn, [tx(evil)], "skip")
    stored = conn.execute("SELECT transaction_id FROM audit_events").fetchone()[0]
    assert stored == evil
    assert count_events(conn) == 1  # table still exists
