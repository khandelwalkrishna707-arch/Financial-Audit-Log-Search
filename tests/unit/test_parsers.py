import json
from decimal import Decimal

import pytest

from audit_search.ingest import iter_records, json_parser
from audit_search.ingest.csv_parser import iter_csv
from audit_search.ingest.json_parser import iter_json, iter_jsonl

# --------------------------------------------------------------------------- CSV


def test_csv_reads_rows_with_line_numbers(fixtures_dir):
    records = list(iter_csv(fixtures_dir / "valid.csv"))
    assert len(records) == 4
    assert records[0].location == "line 2"
    assert records[1].data["amount"] == "1,000.50"  # quoted comma kept inside the field
    assert all(r.error is None for r in records)


def test_csv_flags_rows_with_extra_columns(fixtures_dir):
    records = {r.data.get("transaction_id"): r for r in iter_csv(fixtures_dir / "corrupted.csv")}
    assert "more value" in records["TX-2006"].error
    assert records["TX-2007"].data["account_id"] == "Smith, J"
    assert records["TX-2008"].data["amount"] is None  # short row: missing values are None


def test_csv_handles_excel_bom(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_bytes("﻿transaction_id,event_date\nTX-1,2026-01-01\n".encode())
    (record,) = iter_csv(path)
    assert record.data == {"transaction_id": "TX-1", "event_date": "2026-01-01"}


def test_csv_oversized_field_stops_with_clear_error(tmp_path):
    path = tmp_path / "huge.csv"
    path.write_text("transaction_id,event_date\nTX-1,2026-01-01\nTX-2," + "x" * 200_000 + "\n")
    records = iter_csv(path)
    assert next(records).data["transaction_id"] == "TX-1"  # rows before the problem still come out
    with pytest.raises(ValueError, match="CSV format error near line 3"):
        next(records)


def test_csv_streams_lazily(fixtures_dir):
    iterator = iter_csv(fixtures_dir / "valid.csv")
    assert next(iterator).data["transaction_id"] == "TX-1001"  # no full read needed


# --------------------------------------------------------------------------- JSON


def test_json_array_keeps_decimals_exact(fixtures_dir):
    records = list(iter_json(fixtures_dir / "valid.json"))
    assert [r.location for r in records] == ["record 1", "record 2", "record 3"]
    assert records[0].data["amount"] == Decimal("99.99")


def test_json_wrapped_object(fixtures_dir):
    records = list(iter_json(fixtures_dir / "wrapped.json"))
    assert [r.data["id"] for r in records] == [42, 43]


def test_json_single_object_is_one_record(tmp_path):
    path = tmp_path / "one.json"
    path.write_text('{"transaction_id": "TX-1", "event_date": "2026-01-01"}')
    (record,) = iter_json(path)
    assert record.data["transaction_id"] == "TX-1"


def test_json_wrapped_object_with_unnamed_list(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text('{"meta": 1, "rows": [{"id": 1}, {"id": 2}]}')
    assert len(list(iter_json(path))) == 2


@pytest.mark.parametrize("content", ["", "   \n", "[]", " [ ] "])
def test_json_empty_inputs_give_no_records(tmp_path, content):
    path = tmp_path / "empty.json"
    path.write_text(content)
    assert list(iter_json(path)) == []


def test_json_non_object_items_are_flagged(tmp_path):
    path = tmp_path / "mixed.json"
    path.write_text('[{"id": 1}, 7, "text"]')
    records = list(iter_json(path))
    assert records[0].error is None
    assert "got int" in records[1].error
    assert "got str" in records[2].error


def test_json_array_syntax_error_raises_with_position(fixtures_dir):
    iterator = iter_json(fixtures_dir / "broken_array.json")
    assert next(iterator).data["transaction_id"] == "TX-5001"  # earlier records still come out
    with pytest.raises(ValueError, match="record 2"):
        next(iterator)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ('"just a string"', "array"),
        ('[{"id": 1} {"id": 2}]', "expected ','"),
        ('[{"id": 1}] trailing', "after the end"),
        ('{"pageItems": [', "invalid JSON"),
    ],
)
def test_json_structural_errors(tmp_path, content, message):
    path = tmp_path / "bad.json"
    path.write_text(content)
    with pytest.raises(ValueError, match=message):
        list(iter_json(path))


def test_json_array_streams_across_chunk_boundaries(tmp_path, monkeypatch):
    """Use a tiny chunk size so records (and numbers) are split between reads."""
    monkeypatch.setattr(json_parser, "_CHUNK_SIZE", 7)
    items = [f'  {{"id": "TX-{i}", "amount": {1234567 + i}.89, "n": 1234567}}' for i in range(50)]
    path = tmp_path / "big.json"
    path.write_text("[\n" + ",\n".join(items) + "\n]\n")
    records = list(iter_json(path))
    assert len(records) == 50
    assert records[-1].data == {"id": "TX-49", "amount": Decimal("1234616.89"), "n": 1234567}


def test_json_array_pretty_printed(tmp_path):
    path = tmp_path / "pretty.json"
    path.write_text(json.dumps([{"id": 1}, {"id": 2}], indent=4))
    assert [r.data["id"] for r in iter_json(path)] == [1, 2]


# --------------------------------------------------------------------------- JSON Lines


def test_jsonl_skips_bad_lines_and_continues(fixtures_dir):
    records = list(iter_jsonl(fixtures_dir / "corrupted.jsonl"))
    assert [r.location for r in records] == ["line 1", "line 2", "line 3", "line 5"]
    assert records[0].error is None
    assert "invalid JSON" in records[1].error
    assert "got list" in records[2].error
    assert records[3].data["transaction_id"] == "TX-4004"


# --------------------------------------------------------------------------- dispatch


@pytest.mark.parametrize("name", ["valid.csv", "valid.json", "corrupted.jsonl"])
def test_iter_records_picks_parser_by_extension(fixtures_dir, name):
    assert list(iter_records(fixtures_dir / name))


def test_iter_records_rejects_unknown_extension(tmp_path):
    with pytest.raises(ValueError, match="unsupported file type"):
        iter_records(tmp_path / "log.xml")
