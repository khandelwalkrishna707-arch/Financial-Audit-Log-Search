# Input and export file formats

`audit-search import` reads three kinds of file, chosen by extension. All files must be UTF-8
(a UTF-8 byte-order mark from Excel is fine). Code: [`src/audit_search/ingest/`](../src/audit_search/ingest/).

| Extension | Format |
|---|---|
| `.csv` | Comma-separated, first line is the header. Quote values that contain commas: `"Smith, J"`. |
| `.json` | A JSON array of objects, **or** an object that wraps the array (e.g. `{"pageItems": [...]}` as Apache Fineract returns it). Large arrays are streamed, not loaded at once. |
| `.jsonl` / `.ndjson` | JSON Lines: one object per line. Blank lines are skipped. |

## Fields

Column names are matched ignoring case, spaces, dashes and underscores, so `transactionId`,
`Transaction ID` and `transaction_id` are the same column. For each field the first alias in
the list below that appears in the file is used. Unknown columns are ignored.

| Field | Required | Accepted column names | Stored as |
|---|---|---|---|
| `transaction_id` | yes | transaction_id, txn_id, tx_id, transaction_ref, id | trimmed text, case kept |
| `event_date` | yes | event_date, transaction_date, made_on_date, timestamp, created_at, event_time, date | ISO 8601 UTC text, see [date_formats.md](date_formats.md) |
| `account_id` | no | account_id, account_no, account_number, account | trimmed text |
| `action_type` | no | action_type, action_name, transaction_type, action, type | upper case, spaces and dashes become `_` (`loan-repayment` → `LOAN_REPAYMENT`); `{"value": "Deposit"}` objects are unwrapped |
| `amount` | no | amount, transaction_amount, value | whole cents (`1,234.50` → `123450`); `$ € £ ₹ ¥`, spaces and thousands commas are removed; `(12.50)` is negative |
| `user_id` | no | user_id, maker_id, made_by, maker, user | trimmed text |

The file name is stored as `source_file` on every row.

## Rejected rows

A bad row is skipped with a reason and its location (`line 14` for CSV/JSONL, `record 3` for
JSON); the rest of the file still imports. A row is rejected when:

* `transaction_id` or `event_date` is missing or blank,
* the date is impossible or in an unknown format (`31/02/2026`),
* the amount is not a number, has more than 2 decimal places, or is too large,
* a CSV line has more values than the header has columns,
* a JSON record is not an object, or a JSON Lines line is not valid JSON.

## Duplicates

Two rows with the same `transaction_id`, `event_date` and `action_type` are the same event.
`--on-duplicate skip` (default) keeps the stored row, `--on-duplicate update` overwrites it.

## Minimal examples

```csv
transaction_id,event_date,account_id,action_type,amount,user_id
TX-1001,2026-03-14T09:30:00Z,AC-1,deposit,1250.00,u1
```

```json
[{"transactionId": "TX-1001", "date": "14/03/2026 09:30", "amount": 12.5, "type": {"value": "Deposit"}}]
```

## Export format

`--export out.csv` (CLI), option 4 in the menu and the **Export CSV** button in the web UI
all write the same CSV:

```csv
transaction_id,event_date,account_id,action_type,amount,user_id,source_file
TX-1001,2026-03-14T09:30:00Z,AC-1,DEPOSIT,12.50,u1,valid.csv
```

* The header is always written, in this order, even when there are no results.
* Amounts are written with two decimals (`12.50`); a missing value is an empty cell.
* Dates are ISO 8601 UTC, exactly as stored. Values are quoted by Python's `csv` module, so
  commas and quotes inside values are safe.
