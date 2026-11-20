from decimal import Decimal

import pytest

from audit_search.normalize.fields import (
    cents_to_str,
    clean_text,
    normalize_action,
    parse_amount_cents,
)
from audit_search.normalize.record import to_transaction


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(" AC-1 ", "AC-1"), ("", None), ("   ", None), (None, None), (42, "42")],
)
def test_clean_text(raw, expected):
    assert clean_text(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("deposit", "DEPOSIT"),
        (" Loan Repayment ", "LOAN_REPAYMENT"),
        ("fee-charge", "FEE_CHARGE"),
        ({"id": 1, "value": "Withdrawal"}, "WITHDRAWAL"),
        ({"code": "loanTransactionType.repayment"}, "LOANTRANSACTIONTYPE.REPAYMENT"),
        (None, ""),
        ("", ""),
    ],
)
def test_normalize_action(raw, expected):
    assert normalize_action(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12.50", 1250),
        ("1,234.56", 123456),
        ("₹ 1,000", 100000),
        ("$5", 500),
        ("-7.25", -725),
        ("(7.25)", -725),
        ("0.10", 10),
        ("100.500", 10050),  # trailing zero is fine
        (12, 1200),
        (12.5, 1250),
        (0.1, 10),  # float 0.1 must not become 9 cents
        (Decimal("99.99"), 9999),
        (None, None),
        ("", None),
        ("  ", None),
    ],
)
def test_parse_amount_cents(raw, expected):
    assert parse_amount_cents(raw) == expected


@pytest.mark.parametrize("raw", ["abc", "12.3.4", "1.234", "NaN", "Infinity", True, "1.2.3"])
def test_parse_amount_rejects_bad_values(raw):
    with pytest.raises(ValueError):
        parse_amount_cents(raw)


@pytest.mark.parametrize("raw", ["1e30", 10**30, Decimal("1e999999999"), "-1e17"])
def test_parse_amount_rejects_amounts_too_large_for_sqlite(raw):
    with pytest.raises(ValueError, match="too large"):
        parse_amount_cents(raw)


@pytest.mark.parametrize("raw", ["1e-50", "0.1000000000000000000000000000000001"])
def test_parse_amount_detects_extra_decimals_exactly(raw):
    """`value * 100` would round these after 28 digits and wrongly accept them."""
    with pytest.raises(ValueError, match="decimal places"):
        parse_amount_cents(raw)


def test_parse_amount_largest_storable_value():
    assert parse_amount_cents("92233720368547758.07") == 2**63 - 1


@pytest.mark.parametrize(("cents", "text"), [(1250, "12.50"), (5, "0.05"), (-725, "-7.25"),
                                             (0, "0.00"), (None, "")])
def test_cents_to_str(cents, text):
    assert cents_to_str(cents) == text


def test_to_transaction_builds_clean_record():
    tx = to_transaction(
        {
            "transaction_id": " TX-1 ",
            "event_date": "2026-03-14T15:00:00+05:30",
            "account_id": "AC-1",
            "action_type": "deposit",
            "amount": "10.00",
            "user_id": "",
        },
        source_file="a.csv",
    )
    assert tx.transaction_id == "TX-1"
    assert tx.event_date == "2026-03-14T09:30:00Z"
    assert tx.action_type == "DEPOSIT"
    assert tx.amount_cents == 1000
    assert tx.user_id is None
    assert tx.source_file == "a.csv"


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ({"event_date": "2026-01-01"}, "missing transaction_id"),
        ({"transaction_id": "T", "event_date": "nope"}, "bad event_date"),
        ({"transaction_id": "T", "event_date": "2026-01-01", "amount": "x"}, "bad amount"),
    ],
)
def test_to_transaction_explains_errors(row, message):
    with pytest.raises(ValueError, match=message):
        to_transaction(row)
