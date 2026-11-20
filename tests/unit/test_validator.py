from audit_search.ingest.validator import canonicalize, missing_required


def test_canonicalize_maps_aliases_ignoring_case_and_separators():
    row = canonicalize(
        {
            "Transaction ID": "TX-1",
            "madeOnDate": "2026-01-01",
            "Account-No": "AC-1",
            "actionName": "DEPOSIT",
            "AMOUNT": "1.00",
            "maker": "admin",
            "unrelated_column": "ignored",
        }
    )
    assert row == {
        "transaction_id": "TX-1",
        "event_date": "2026-01-01",
        "account_id": "AC-1",
        "action_type": "DEPOSIT",
        "amount": "1.00",
        "user_id": "admin",
    }


def test_specific_alias_beats_generic_alias():
    row = canonicalize({"id": "audit-row-7", "transaction_id": "TX-1", "date": "x"})
    assert row["transaction_id"] == "TX-1"


def test_generic_id_is_used_when_nothing_better_exists():
    assert canonicalize({"id": 42})["transaction_id"] == 42


def test_non_string_keys_are_ignored():
    assert canonicalize({None: ["extra"], "id": "1"}) == {"transaction_id": "1"}


def test_missing_required_reports_absent_and_blank_fields():
    assert missing_required({"transaction_id": "TX", "event_date": "2026"}) == []
    assert missing_required({"transaction_id": "  "}) == ["transaction_id", "event_date"]
    assert missing_required({"transaction_id": 0, "event_date": None}) == ["event_date"]
