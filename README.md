# Financial Audit Log Search

An offline Python command-line tool that imports financial audit logs (CSV / JSON), cleans them,
indexes them in a local SQLite database, and lets reviewers search by transaction ID or date range
and export the results to CSV.

Nothing is uploaded anywhere: the data stays on your machine. The core tool uses only the Python
standard library.

> Project G395 – Open Source Developer OJT (4-week track).
> The tool indexes and retrieves records. It does **not** validate financial correctness,
> reconcile ledgers or replace an official audit sign-off.

## Status

| Part | State |
|---|---|
| Import CSV / JSON / JSON Lines, validation, date + amount normalization | ✅ done |
| SQLite storage, indexes, 1,000-row batches, duplicate policy (skip / update) | ✅ done |
| Tests (unit, integration, end-to-end), CI with 85% coverage gate | ✅ done |
| Search by transaction ID (exact / prefix) and date range | ✅ done (#2) |
| Terminal table + CSV export, interactive menu, benchmark script | 🚧 week 2 |
| Flask dashboard on localhost (stretch goal) | ⏳ later |

See [docs/remaining_work.md](docs/remaining_work.md) for the week 2 plan.

## Quick start

Requires Python 3.10 or newer.

```bash
git clone https://github.com/khandelwalkrishna707-arch/Financial-Audit-Log-Search.git
cd Financial-Audit-Log-Search
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e . -r requirements-dev.txt

audit-search import --file data/samples/audit_sample.csv
```

Example output:

```
Imported audit_sample.csv in 0.02s
  rows read          : 500
  inserted           : 473
  duplicates skipped : 10
  duplicates updated : 0
  rejected           : 17
Rejected rows (first 17):
  line 24: bad event_date: impossible date or unknown format: '31/02/2026'
  line 28: missing transaction_id
  ...
```

## Commands

```bash
audit-search import --file <path> [--on-duplicate skip|update] [--db audit.db]
audit-search find   --id TX-98721 [--prefix]
audit-search range  --from 2026-01-01 --to 2026-03-31
audit-search menu                                       # week 2
# --export out.csv on find / range                      # week 2
```

* `find --prefix` matches IDs that start with the text; `%` and `_` are ordinary characters.
* `range` includes **both** days completely: `--to 2026-03-31` includes events up to
  `2026-03-31T23:59:59Z`. Search dates accept the same formats as imported dates.
* Results are sorted by event date, then transaction ID. On 10,000 records an ID lookup takes
  well under 1 ms and a one-month range about 2 ms (target: under 50 ms).

`python -m audit_search ...` works too. The database defaults to `audit.db` in the current folder
(override with `--db` or the `AUDIT_SEARCH_DB` environment variable).

## Rules the tool follows

* **Dates** are stored as ISO 8601 UTC, e.g. `2026-03-14T09:30:00Z`. Dates with a timezone are
  converted; dates without one are treated as UTC; `03/04/2026` is **3 April** (day first).
  Full list: [docs/date_formats.md](docs/date_formats.md).
* **Amounts** are stored as whole cents (`12.50` → `1250`) so money never gets float rounding errors.
  Amounts with more than 2 decimal places are rejected rather than silently rounded.
* **Duplicates**: the same `transaction_id` + `event_date` + `action_type` is the same event.
  `--on-duplicate skip` (default) keeps the stored row; `update` overwrites it. Both are counted.
* **Bad rows** (missing ID or date, impossible date, non-numeric amount, extra CSV columns) are
  rejected with a reason and line number. The rest of the file still imports.
* **Column names** are matched flexibly: `transactionId`, `Transaction ID`, `txn_id` all work.
  See `FIELD_ALIASES` in `src/audit_search/ingest/validator.py`.

## Development

```bash
pytest --cov          # all tests + coverage report (fails below 85%)
ruff check .          # lint
python scripts/generate_synthetic_data.py --rows 10000   # fake data in data/generated/
```

Only synthetic data is committed (`data/samples/`). Never commit real audit logs or `.db` files;
`.gitignore` blocks them.

More detail: [docs/PROJECT_EXPLANATION.md](docs/PROJECT_EXPLANATION.md).
