"""Search queries (issue #2): exact ID, prefix and inclusive date range."""

import sqlite3

import pytest

from audit_search.models import Transaction
from audit_search.search import queries
from audit_search.search.queries import (
    date_range_bounds,
    find_by_date_range,
    find_by_id,
    find_by_prefix,
    row_to_transaction,
)
from audit_search.storage.database import init_schema, insert_batch


def event(tx_id, date, action="DEPOSIT"):
    return Transaction(tx_id, date, "AC-1", action, 100, "u1", "t.csv")


@pytest.fixture
def db(conn):
    insert_batch(
        conn,
        [
            event("TX-1", "2026-03-31T23:59:59Z"),  # last second of March 31
            event("TX-1", "2026-01-01T00:00:00Z", "WITHDRAWAL"),  # first second of the year
            event("TX-10", "2026-02-15T12:00:00Z"),
            event("TX-100", "2026-04-01T00:00:00Z"),  # first second AFTER Q1
            event("TX-2", "2025-12-31T23:59:59Z"),  # last second BEFORE Q1
            event("A%B", "2026-02-01T00:00:00Z"),
            event("AXB", "2026-02-01T00:00:00Z"),
            event("A_B", "2026-02-02T00:00:00Z"),
            event("tx-1", "2026-02-03T00:00:00Z"),
        ],
        "skip",
    )
    return conn


def ids(results):
    return [tx.transaction_id for tx in results]


# --------------------------------------------------------------------------- exact ID


def test_find_by_id_returns_every_event_for_that_id_and_nothing_else(db):
    results = find_by_id(db, "TX-1")
    assert ids(results) == ["TX-1", "TX-1"]  # not TX-10, TX-100 or tx-1
    assert [tx.event_date for tx in results] == ["2026-01-01T00:00:00Z", "2026-03-31T23:59:59Z"]


def test_find_by_id_returns_complete_transactions(db):
    (tx,) = find_by_id(db, "TX-10")
    assert tx == event("TX-10", "2026-02-15T12:00:00Z")


def test_find_by_id_trims_spaces_and_is_case_sensitive(db):
    assert ids(find_by_id(db, "  TX-2 ")) == ["TX-2"]
    assert ids(find_by_id(db, "tx-1")) == ["tx-1"]


def test_find_by_id_without_match(db):
    assert find_by_id(db, "TX-999") == []


@pytest.mark.parametrize("search", [find_by_id, find_by_prefix])
def test_empty_id_or_prefix_is_refused(db, search):
    with pytest.raises(ValueError, match="must not be empty"):
        search(db, "   ")


def test_sql_injection_input_is_just_text(db):
    assert find_by_id(db, "TX-1' OR '1'='1") == []
    assert len(find_by_id(db, "TX-1")) == 2  # table untouched


# --------------------------------------------------------------------------- prefix


def test_prefix_matches_ids_that_start_with_it(db):
    results = find_by_prefix(db, "TX-1")
    assert sorted(set(ids(results))) == ["TX-1", "TX-10", "TX-100"]
    assert len(results) == 4
    assert [tx.event_date for tx in results] == sorted(tx.event_date for tx in results)


@pytest.mark.parametrize(("prefix", "expected"), [("A%", ["A%B"]), ("A_", ["A_B"]), ("A", None)])
def test_percent_and_underscore_are_not_wildcards(db, prefix, expected):
    found = ids(find_by_prefix(db, prefix))
    assert found == (expected or ["A%B", "AXB", "A_B"])


def test_prefix_is_case_sensitive(db):
    assert "tx-1" not in ids(find_by_prefix(db, "TX-"))


@pytest.mark.parametrize(
    ("prefix", "upper"),
    [("TX-98", "TX-99"), ("AB~", "AB\x7f"), ("X" + chr(0xD7FF), "X" + chr(0xE000))],
)
def test_prefix_upper_bound(prefix, upper):
    assert queries._prefix_upper_bound(prefix) == upper


def test_prefix_ending_with_last_unicode_character_is_refused():
    with pytest.raises(ValueError, match="unsupported character"):
        queries._prefix_upper_bound("A" + chr(0x10FFFF))


# --------------------------------------------------------------------------- date range

Q1 = ["TX-1", "A%B", "AXB", "A_B", "tx-1", "TX-10", "TX-1"]  # sorted by date, then ID


def test_date_range_includes_both_whole_days_and_is_sorted(db):
    assert ids(find_by_date_range(db, "2026-01-01", "2026-03-31")) == Q1


@pytest.mark.parametrize(
    ("start", "end"),
    [("01/01/2026", "31/03/2026"), ("20260101", "20260331"), ("1 January 2026", "31 Mar 2026")],
)
def test_date_range_accepts_the_same_formats_as_import(db, start, end):
    assert ids(find_by_date_range(db, start, end)) == Q1


def test_end_with_a_time_is_inclusive_to_that_second(db):
    assert "TX-1" in ids(find_by_date_range(db, "2026-03-31", "2026-03-31T23:59:59Z"))
    assert find_by_date_range(db, "2026-03-31", "2026-03-31T23:59:58Z") == []


def test_end_with_timezone_is_converted_to_utc(db):
    # 05:30 in India on 1 April is exactly 00:00:00Z on 1 April -> TX-100 is included
    results = find_by_date_range(db, "2026-04-01", "2026-04-01T05:30:00+05:30")
    assert ids(results) == ["TX-100"]


def test_single_day(db):
    assert ids(find_by_date_range(db, "2026-03-31", "2026-03-31")) == ["TX-1"]


@pytest.mark.parametrize(
    ("start", "end", "bounds"),
    [
        ("2026-03-31", "2026-03-31", ("2026-03-31T00:00:00Z", "2026-04-01T00:00:00Z")),
        ("2026-03-31", "2026-03-31 10:00", ("2026-03-31T00:00:00Z", "2026-03-31T10:00:01Z")),
        ("2026-03-31", "2026-03-31T00:00:00Z", ("2026-03-31T00:00:00Z", "2026-03-31T00:00:01Z")),
        ("2026-03-14", "1773480600", ("2026-03-14T00:00:00Z", "2026-03-14T09:30:01Z")),
        ("2026-03-31", "2026-03-31T10:00:00.9Z", ("2026-03-31T00:00:00Z", "2026-03-31T10:00:01Z")),
    ],
)
def test_date_range_bounds(start, end, bounds):
    assert date_range_bounds(start, end) == bounds


@pytest.mark.parametrize(
    ("start", "end", "message"),
    [
        ("2026-04-01", "2026-03-31", "is after end date"),
        ("2026-03-31T10:00:00Z", "2026-03-31T09:59:59Z", "is after end date"),
        ("yesterday", "2026-03-31", "bad start date"),
        ("2026-03-01", "31/02/2026", "bad end date"),
    ],
)
def test_bad_date_ranges_give_clear_errors(db, start, end, message):
    with pytest.raises(ValueError, match=message):
        find_by_date_range(db, start, end)


# --------------------------------------------------------------------------- indexes


@pytest.mark.parametrize(
    ("sql", "params", "index"),
    [
        (queries._BY_ID_SQL, ("TX-1",), "sqlite_autoindex_audit_events_1"),
        (queries._BY_PREFIX_SQL, ("TX-1", "TX-2"), "sqlite_autoindex_audit_events_1"),
        (queries._BY_DATE_RANGE_SQL, ("2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z"),
         "idx_tx_date"),
    ],
)
def test_every_query_uses_an_index(db, sql, params, index):
    plan = " ".join(row[3] for row in db.execute("EXPLAIN QUERY PLAN " + sql, params))
    assert f"USING INDEX {index}" in plan, plan


def test_queries_work_on_a_plain_connection():
    """Callers don't have to set row_factory themselves."""
    plain = sqlite3.connect(":memory:")
    init_schema(plain)
    insert_batch(plain, [event("TX-1", "2026-01-01T00:00:00Z")], "skip")
    assert ids(find_by_id(plain, "TX-1")) == ["TX-1"]
    plain.close()


def test_row_to_transaction_ignores_the_id_column(db):
    db_row = db.execute("SELECT * FROM audit_events WHERE transaction_id = 'TX-10'").fetchone()
    assert row_to_transaction(db_row) == event("TX-10", "2026-02-15T12:00:00Z")
