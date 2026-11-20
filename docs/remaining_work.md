# Remaining work: the search half (week 2)

The **import half** is finished and tested: files go in, clean rows land in SQLite.
Your half is the **search half**, the right-hand path of the PRD workflow diagram:

```
search criteria → validate → parameterized SQL → indexed lookup → sort → terminal table / CSV
```

Do the tasks in this order. Each one is a small GitHub issue + branch + PR, e.g.
`feature/search-queries`. Write the tests in the same PR as the code; CI fails below 85% coverage.

You can always look at the database directly while you work:

```bash
audit-search import --file data/samples/audit_sample.csv
sqlite3 audit.db "SELECT * FROM audit_events ORDER BY event_date LIMIT 5;"
```

---

## 1. `search/queries.py`: the queries ⭐ most important

Stubs with signatures and docstrings are already in the file.

**`row_to_transaction(row)`**: the columns have the same names as the `Transaction` fields, so
`Transaction(**dict(row))` almost works. You need to leave out the `id` column.

**`find_by_id(conn, transaction_id)`**

```sql
SELECT ... FROM audit_events WHERE transaction_id = ? ORDER BY event_date, action_type
```

Strip whitespace from the input first.

**`find_by_prefix(conn, prefix)`** ⚠️ trap. `WHERE transaction_id LIKE ?` with `prefix + "%"`
looks right but has two problems:
1. A `%` or `_` typed by the user acts as a wildcard, so the search returns the wrong rows.
2. SQLite's `LIKE` is case-insensitive, so it **can't use the index** on a normal column. Every
   search then reads the whole table and you miss the 50 ms target on big databases.

Use a range instead, which uses the index and has no wildcards:

```python
upper = prefix[:-1] + chr(ord(prefix[-1]) + 1)   # "TX-98" -> "TX-99"
# WHERE transaction_id >= ? AND transaction_id < ?     params: (prefix, upper)
```

Refuse an empty prefix with a `ValueError`; otherwise it would return everything.

**`find_by_date_range(conn, start, end)`** ⚠️ trap. Normalize both values with
`normalize_date()` from `normalize/dates.py`. Then:
- `--to 2026-03-31` normalizes to `2026-03-31T00:00:00Z`, i.e. **midnight at the start** of March 31.
  `BETWEEN` would miss everything later that day. If the user gave a date with no time, compare
  with `event_date < <next day at 00:00:00Z>` instead. Tip: check whether the `datetime` from
  `parse_datetime()` is exactly midnight **and** the input text has no `:` in it.
- If start is after end, raise `ValueError("start date is after end date")`.
- `ORDER BY event_date, transaction_id, action_type`

Check that SQLite uses the index:

```bash
sqlite3 audit.db "EXPLAIN QUERY PLAN SELECT * FROM audit_events WHERE event_date >= '2026-01-01' AND event_date < '2026-02-01';"
# should say: SEARCH audit_events USING INDEX idx_tx_date
```

**Tests:** `tests/unit/test_queries.py`. Use the `conn` fixture, insert rows with
`storage.database.insert_batch`, and test: exact hit, no hit, prefix, prefix containing `%`,
the whole last day being included, start > end, the same day given in different formats, and
sort order.

## 2. `export/csv_writer.py` and `export/formatter.py`

Read the docstrings in each file. Key points:
- Always write the header, even for 0 rows. Use `csv.writer`, never `",".join()`.
- Write the amount with `cents_to_str()` from `normalize/fields.py`.
- Catch `OSError` and raise a clear error the CLI can print.
- **Data-integrity test (PRD target):** import `tests/fixtures/valid.csv`, export it, read the
  export back with `csv.DictReader`, and check every value. Include the `"Smith, J"` row from
  `corrupted.csv` to prove quoting works.

## 3. `cli.py`: connect `find` and `range`

The argument parsers already exist. Replace `handler=_not_built_yet` with real handlers that:
open the DB, call the query, print `format_table(...)`, and if `--export` is given call
`write_csv(...)`. Catch `ValueError` (bad date, empty prefix) and print `error: ...` with
exit code 1, like `cmd_import` does. Update the tests in `tests/e2e/test_cli.py`, because the
"not built yet" test will then fail. That's expected.

## 4. `menu.py`: interactive menu

See the docstring. Make it testable: have `run_menu` take `input_func=input` and
`print_func=print` parameters. Tests can then pass fake functions instead of typing.

## 5. `scripts/benchmark.py`: prove the targets

1. Generate 10,000 rows with `generate_synthetic_data.make_rows`.
2. Time `import_file` (target < 3.0 s; currently about 0.15 s).
3. Time 100 `find_by_id` calls and 100 one-month `find_by_date_range` calls, and print the
   average and the worst time (target < 50 ms).

Put the numbers in the README.

## 6. Docs and repo hygiene

- `docs/data_privacy.md`: data stays local, real logs never go in Git, delete `audit.db` when
  done, the web UI only binds to 127.0.0.1.
- `CONTRIBUTING.md`: setup, branch naming, commit style (`feat(search): ...`), "tests + ruff
  must pass".
- `LICENSE`: choose one with your mentor (MIT and Apache-2.0 are common; Fineract uses Apache-2.0).
- README: change the 🚧 rows to ✅ and add search examples.
- Tag `v1.0.0` when everything passes.

## 7. Stretch goals (only if time is left)

- Flask dashboard in `src/audit_search/web/`, `app.run(host="127.0.0.1", port=5000)`. Reuse
  `search/` and `export/`, with no SQL in the web code.
- Extra filters (user ID, action type, amount range). Note that amounts are stored in **cents**.
- Batch import: loop `import_file` over `Path(folder).glob("*.csv")` and similar patterns.
- Import provenance: the file hash (`hashlib.sha256`) and import time as new columns.
