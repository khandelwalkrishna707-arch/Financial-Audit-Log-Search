from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from audit_search.normalize.dates import normalize_date, parse_datetime


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # ISO 8601 variants
        ("2026-03-14T09:30:00Z", "2026-03-14T09:30:00Z"),
        ("2026-03-14T09:30:00z", "2026-03-14T09:30:00Z"),
        ("2026-03-14T09:30:00.123Z", "2026-03-14T09:30:00Z"),
        ("2026-03-14T09:30:00+00:00", "2026-03-14T09:30:00Z"),
        ("2026-03-14 09:30:00", "2026-03-14T09:30:00Z"),
        ("2026-03-14", "2026-03-14T00:00:00Z"),
        ("  2026-03-14T09:30:00Z  ", "2026-03-14T09:30:00Z"),
        # timezones are converted to UTC
        ("2026-03-14T15:00:00+05:30", "2026-03-14T09:30:00Z"),
        ("2026-03-14T15:00:00+0530", "2026-03-14T09:30:00Z"),
        ("2026-03-14T01:00:00-05:00", "2026-03-14T06:00:00Z"),
        ("2026-03-14T02:00:00+05:30", "2026-03-13T20:30:00Z"),  # crosses midnight backwards
        # day-first formats
        ("14/03/2026", "2026-03-14T00:00:00Z"),
        ("14/03/2026 09:30", "2026-03-14T09:30:00Z"),
        ("14/03/2026 09:30:00", "2026-03-14T09:30:00Z"),
        ("03/04/2026", "2026-04-03T00:00:00Z"),  # 3 April, NOT 4 March
        ("14-03-2026", "2026-03-14T00:00:00Z"),
        ("2026/03/14 09:30:00", "2026-03-14T09:30:00Z"),
        ("20260314", "2026-03-14T00:00:00Z"),
        # Fineract-style written dates
        ("14 March 2026", "2026-03-14T00:00:00Z"),
        ("14 Mar 2026", "2026-03-14T00:00:00Z"),
        # epoch timestamps (seconds and milliseconds, numbers and text)
        ("1773480600", "2026-03-14T09:30:00Z"),
        (1773480600, "2026-03-14T09:30:00Z"),
        (1773480600000, "2026-03-14T09:30:00Z"),
        (Decimal("1773480600.5"), "2026-03-14T09:30:00Z"),
        (20260314, "2026-03-14T00:00:00Z"),  # 8-digit number is YYYYMMDD, not a 1970 timestamp
        # Fineract JSON date lists
        ([2026, 3, 14], "2026-03-14T00:00:00Z"),
        ([2026, 3, 14, 9, 30, 0], "2026-03-14T09:30:00Z"),
    ],
)
def test_normalize_date_accepts_known_formats(raw, expected):
    assert normalize_date(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        None, "", "   ", "not a date", "31/02/2026", "2026-13-01", "14/03/26x",
        True, [2026, 3], [2026, "3", 14], [2026, 2, 30], {"y": 2026},
        # numbers that are placeholders or impossible, never real audit timestamps
        0, 5, -5, "0", float("nan"), float("inf"), 10**20, 10**400, [10**20, 1, 1],
    ],
)
def test_normalize_date_rejects_bad_values(raw):
    with pytest.raises(ValueError):
        normalize_date(raw)


def test_output_sorts_alphabetically_in_time_order():
    inputs = ["2026-03-14T15:00:00+05:30", "13/03/2026 23:00:00", "2026-03-14T10:00:00Z"]
    normalized = [normalize_date(value) for value in inputs]
    assert sorted(normalized) == [
        "2026-03-13T23:00:00Z",
        "2026-03-14T09:30:00Z",
        "2026-03-14T10:00:00Z",
    ]


def test_naive_dates_can_use_another_assumed_timezone():
    ist = timezone(timedelta(hours=5, minutes=30))
    assert normalize_date("2026-03-14 15:00:00", assume_tz=ist) == "2026-03-14T09:30:00Z"


def test_datetime_objects_are_accepted():
    aware = datetime(2026, 3, 14, 9, 30, tzinfo=timezone.utc)
    assert parse_datetime(aware) == aware
    assert parse_datetime(datetime(2026, 3, 14)).tzinfo is timezone.utc
