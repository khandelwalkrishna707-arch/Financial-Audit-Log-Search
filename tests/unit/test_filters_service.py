"""Filters on top of searches, and the shared search service."""

import pytest

from audit_search.models import Transaction
from audit_search.search.filters import Filters
from audit_search.search.service import search
from audit_search.storage.database import insert_batch

ROWS = [
    Transaction("TX-1", "2026-01-05T10:00:00Z", "AC-1", "DEPOSIT", 1000, "u1"),
    Transaction("TX-2", "2026-01-06T10:00:00Z", "AC-2", "WITHDRAWAL", 5000, "u2"),
    Transaction("TX-3", "2026-01-07T10:00:00Z", "AC-1", "DEPOSIT", None, "u2"),
    Transaction("TX-30", "2026-02-01T10:00:00Z", "AC-3", "FEE", 250, "u3"),
]


@pytest.fixture
def filled(conn):
    insert_batch(conn, ROWS, "skip")
    return conn


def ids(results):
    return [tx.transaction_id for tx in results]


def test_from_text_normalizes_input():
    f = Filters.from_text(" AC-1 ", "", "loan-repayment", "1,000.50", None)
    assert f == Filters(account_id="AC-1", action_type="LOAN_REPAYMENT", min_cents=100050)
    assert f.active
    assert not Filters.from_text().active


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"min_amount": "abc"}, "bad minimum amount"),
        ({"max_amount": "1.234"}, "bad maximum amount"),
        ({"min_amount": "10", "max_amount": "5"}, "larger than maximum"),
    ],
)
def test_bad_filters(kwargs, message):
    with pytest.raises(ValueError, match=message):
        Filters.from_text(**kwargs)


@pytest.mark.parametrize(
    "filters, expected",
    [
        (Filters(account_id="AC-1"), ["TX-1", "TX-3"]),
        (Filters(user_id="u2"), ["TX-2", "TX-3"]),
        (Filters(action_type="DEPOSIT"), ["TX-1", "TX-3"]),
        (Filters(min_cents=1000), ["TX-1", "TX-2"]),  # missing amount never matches
        (Filters(max_cents=1000), ["TX-1", "TX-30"]),
        (Filters(account_id="AC-1", min_cents=1), ["TX-1"]),
    ],
)
def test_filters_on_a_date_range(filled, filters, expected):
    assert ids(search(filled, start="2026-01-01", end="2026-02-28", filters=filters)) == expected


def test_search_by_id_and_prefix(filled):
    assert ids(search(filled, transaction_id="TX-3")) == ["TX-3"]
    assert ids(search(filled, transaction_id="TX-3", prefix=True)) == ["TX-3", "TX-30"]
    assert ids(search(filled, transaction_id="TX-3", prefix=True,
                      filters=Filters(action_type="FEE"))) == ["TX-30"]


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({}, "give a transaction ID or a date range"),
        ({"transaction_id": "TX-1", "start": "2026-01-01"}, "not both"),
        ({"start": "2026-01-01"}, "needs both"),
        ({"end": "2026-01-01"}, "needs both"),
        ({"transaction_id": " "}, "must not be empty"),
    ],
)
def test_bad_criteria(filled, kwargs, message):
    with pytest.raises(ValueError, match=message):
        search(filled, **kwargs)
