# Financial Audit Log Search: Project Explanation

*Project G395 · Open Source Developer OJT · progress after week 1*

---

## 1. The project in one minute

Banks and microfinance platforms such as **Apache Fineract** and **Mifos** record every money
event: deposits, withdrawals, loan disbursements and repayments. They export these records as
**audit logs**: very large CSV or JSON files.

When an auditor needs to answer *"what happened to transaction TX-98721?"* or *"show me every
event in the first quarter"*, they have to scroll through these huge files by hand. That is slow,
and it is easy to miss records, because:

- dates are written in **different formats and timezones** (`14/03/2026`, `2026-03-14T15:00+05:30`,
  `1773480600`...), so a simple text search misses matches;
- overlapping exports contain the **same transaction twice**;
- some rows are **broken** (missing ID, impossible date, text where a number should be);
- uploading the files to a cloud tool would **expose private financial data**.

**My tool fixes this.** It is a command-line program that:

1. **imports** the log files,
2. **cleans** every record (one date format, exact money amounts, bad rows reported),
3. **stores** them in a local, indexed **SQLite** database,
4. **searches** them by transaction ID or date range in milliseconds,
5. **exports** the results as a clean CSV file.

Everything runs **offline on the user's own computer**. No data leaves the machine.

---

## 2. Languages and technologies used

### Languages

| Language | Where it is used | Why |
|---|---|---|
| **Python 3.10+** | All the application code, tests and scripts | Readable, and its standard library already has CSV, JSON, dates, SQLite and command-line parsing built in |
| **SQL** (SQLite dialect) | `storage/schema.sql` (table and indexes) and the queries in `storage/duplicates.py` | The standard language for creating tables, inserting rows and searching with indexes |
| **YAML** | `.github/workflows/ci.yml` | The format GitHub Actions uses to describe the automatic test pipeline |
| **TOML** | `pyproject.toml` | The standard Python format for project metadata, dependencies and tool settings |
| **Markdown** | `README.md`, `docs/` | Documentation that GitHub displays nicely |
| **CSV / JSON** | Input data, sample files, test fixtures | These are the formats the audit logs come in |

### Python standard-library modules (built in, nothing to install)

| Module | What I use it for |
|---|---|
| `sqlite3` | Talking to the SQLite database |
| `csv` | Reading CSV files safely (quoted commas, line breaks inside fields) |
| `json` | Reading JSON. I use its low-level `raw_decode` to stream big arrays record by record |
| `datetime` | Parsing dates and converting timezones to UTC |
| `decimal` | Exact money values (avoids float errors such as `0.1 + 0.2 = 0.30000000000000004`) |
| `argparse` | The command-line interface (`import`, `find`, `range`, `menu`) |
| `dataclasses` | The `Transaction` data model shared by every layer |
| `pathlib`, `importlib.resources` | File paths, and loading `schema.sql` from inside the package |
| `re`, `enum`, `collections` | Text cleaning, the duplicate outcomes (`INSERTED / UPDATED / SKIPPED`), counting |

**The core tool has zero third-party dependencies.** Anyone with Python can install it in seconds.

### Developer tools

| Tool | Purpose |
|---|---|
| **pytest** | Runs the 168 automated tests |
| **pytest-cov / coverage.py** | Measures how much of the code the tests run (currently **97%**, target 85%) |
| **ruff** | Linter: checks code style and common mistakes |
| **Git + GitHub** | Version control, pull requests, code review |
| **GitHub Actions** | CI: runs the linter and the tests on Python 3.10, 3.11, 3.12 and 3.13 on every push |
| **venv** | An isolated Python environment for the project |

---

## 3. Architecture: how the code is organised

The code is split into **layers**. Each layer has one job and only talks to the layer next to it.
That means each part can be tested on its own, and a bug in date parsing is fixed in one file
without touching anything else.

```
                ┌──────────────────────────────┐
                │  CLI  (cli.py)  / menu.py    │  reads the user's command, prints results
                └──────────────┬───────────────┘
                               │
              ┌────────────────┴────────────────┐
              ▼   IMPORT PATH (done)            ▼   SEARCH PATH (week 2)
   ┌─────────────────────┐            ┌─────────────────────┐
   │ ingest/             │            │ search/queries.py   │
   │  csv_parser.py      │            │  by ID, by prefix,  │
   │  json_parser.py     │            │  by date range      │
   │  validator.py       │            └──────────┬──────────┘
   └─────────┬───────────┘                       │
             ▼                                   │
   ┌─────────────────────┐                       │
   │ normalize/          │                       │
   │  dates.py  fields.py│                       │
   │  record.py          │                       │
   └─────────┬───────────┘                       │
             ▼                                   ▼
   ┌───────────────────────────────────────────────────────┐
   │ storage/   schema.sql · database.py · duplicates.py   │
   │            SQLite file: audit_events table + indexes  │
   └───────────────────────────────────────────────────────┘
                                                 │
                                                 ▼
                                   ┌─────────────────────────┐
                                   │ export/ formatter.py    │ terminal table
                                   │         csv_writer.py   │ CSV file
                                   └─────────────────────────┘
```

`importer.py` connects the import path together: **read → validate → normalize → store → summary**.

### Folder guide

| Path | Responsibility |
|---|---|
| `src/audit_search/models.py` | `Transaction` and `ImportSummary` data classes, the shared "language" between layers |
| `src/audit_search/config.py` | Settings: database path, batch size 1,000, duplicate policies |
| `src/audit_search/ingest/` | Reads files **lazily** (row by row) and maps different column names to ours |
| `src/audit_search/normalize/` | Converts dates to UTC, amounts to cents, action names to `UPPER_CASE` |
| `src/audit_search/storage/` | Database schema, batched inserts, duplicate policy |
| `src/audit_search/importer.py` | The import pipeline |
| `src/audit_search/cli.py` | The `audit-search` command |
| `src/audit_search/search/`, `export/`, `menu.py` | Week 2: stubs with documented function signatures |
| `tests/unit/` | Tests for each small piece (dates, amounts, parsers, storage, SQL safety) |
| `tests/integration/` | Whole import: file in → check the database |
| `tests/e2e/` | Runs the real CLI, including the 10,000-row speed test |
| `tests/fixtures/` | Small valid and deliberately broken sample files |
| `scripts/generate_synthetic_data.py` | Generates **fake** audit logs (no real customer data, ever) |
| `data/samples/` | Small synthetic sample files for demos |

---

## 4. How an import works, step by step

Command:

```bash
audit-search import --file data/samples/audit_sample.csv --on-duplicate skip
```

Let's follow **one row** through the system:

```
TX-000002,2026-05-28T15:46:13+05:30,AC-2537,repayment,"2,378.95",user25
```

| Step | File | What happens | Result |
|---|---|---|---|
| 1. Check the file | `importer.py` | Does the file exist? Choose a parser from the extension (`.csv`, `.json`, `.jsonl`) | CSV parser chosen |
| 2. Read lazily | `ingest/csv_parser.py` | `csv.DictReader` reads **one row at a time** with a Python generator (`yield`), so a 5 GB file uses almost no memory | `{"transaction_id": "TX-000002", "event_date": "2026-05-28T15:46:13+05:30", ...}` |
| 3. Map column names | `ingest/validator.py` | `transactionId`, `Transaction ID` and `txn_id` all become `transaction_id` | same dict, standard keys |
| 4. Check required fields | `ingest/validator.py` | Transaction ID and date must exist. If not, the row is **rejected with its line number**, and the import continues | ✅ passes |
| 5. Normalize the date | `normalize/dates.py` | Parse it, convert `+05:30` to UTC | `2026-05-28T10:16:13Z` |
| 6. Normalize the amount | `normalize/fields.py` | Remove the comma, parse with `Decimal`, convert to cents | `237895` |
| 7. Normalize the action | `normalize/fields.py` | Trim and upper-case it | `REPAYMENT` |
| 8. Build a Transaction | `normalize/record.py` | All the clean values go into one `Transaction` object | `Transaction(...)` |
| 9. Batch | `importer.py` | Collect up to 1,000 transactions | |
| 10. Store | `storage/database.py`, `duplicates.py` | One database transaction per batch. `INSERT ... ON CONFLICT DO NOTHING`. If the row already exists, apply the policy: **skip** or **update** | Row saved |
| 11. Summary | `cli.py` | Print the counts and the reasons for rejected rows | see below |

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
```

---

## 5. The database

```sql
CREATE TABLE IF NOT EXISTS audit_events (
    id             INTEGER PRIMARY KEY,
    transaction_id TEXT    NOT NULL,
    event_date     TEXT    NOT NULL,            -- ISO 8601 UTC: 2026-03-14T09:30:00Z
    account_id     TEXT,
    action_type    TEXT    NOT NULL DEFAULT '', -- DEPOSIT, WITHDRAWAL, ...
    amount_cents   INTEGER,                     -- 12.50 is stored as 1250
    user_id        TEXT,
    source_file    TEXT,
    UNIQUE (transaction_id, event_date, action_type)
);
CREATE INDEX IF NOT EXISTS idx_tx_date ON audit_events (event_date);
```

**Why searches are fast:** SQLite builds a **B-tree index** for the `UNIQUE` constraint, and
because it *starts with* `transaction_id`, it serves every ID lookup. I checked this with
`EXPLAIN QUERY PLAN`:

```
SEARCH audit_events USING INDEX sqlite_autoindex_audit_events_1 (transaction_id=?)
```

`idx_tx_date` serves date-range searches. A B-tree lookup takes about *log₂(n)* steps: around
14 steps for 10,000 rows and around 20 for 1,000,000. Search time stays almost flat as the data
grows.

**Why dates are stored as text:** every date has exactly the same format and timezone
(`YYYY-MM-DDTHH:MM:SSZ`), so **alphabetical order is the same as time order**. A normal text
index therefore works perfectly for date ranges.

---

## 6. Important design decisions (and why)

| Decision | Why |
|---|---|
| **Streaming parsers** (generators with `yield`) | Memory stays flat even for files larger than RAM |
| **Normalize once, at import time** | Every stored date is already UTC, so searches are simple and exact |
| **Money as integer cents, parsed with `Decimal`** | Floats cannot store `0.10` exactly. For audit data, the export must match the source to the cent |
| **Reject amounts with more than 2 decimals** instead of rounding | Silently changing someone's money is worse than reporting the row |
| **1,000 rows per database transaction** | SQLite writes to disk once per batch, not once per row. 10,000 rows import in about **0.15 s** (target: under 3 s) |
| **All-or-nothing batches** (`BEGIN` / `COMMIT` / `ROLLBACK`) | A crash never leaves half a batch in the database |
| **Parameterized SQL only** (`?` placeholders) | Prevents SQL injection. A test (`test_sql_safety.py`) reads the source code and **fails the build** if anyone writes SQL with f-strings or `+` |
| **Duplicate key = ID + date + action** | One loan can have several events (disbursement, repayment), and those are *not* duplicates. The same event exported twice *is* a duplicate |
| **`ON CONFLICT DO NOTHING`** rather than `INSERT OR IGNORE` | `OR IGNORE` would also silently hide other errors, such as a missing required value |
| **Flexible column names** | Real exports name columns differently; Fineract uses `madeOnDate`, `actionName`, `maker` |
| **Bad rows are counted, never crash the import** | One broken row shouldn't stop 9,999 good ones, and the auditor sees exactly which rows were skipped and why |
| **Only the Python standard library** | Nothing extra to install and nothing to break; works offline |
| **SQLite** (not PostgreSQL / MongoDB / Elasticsearch) | Single file, no server, no passwords. Ideal for one user on one machine |

---

## 7. Where I improved on the original design document

While building, I found six problems in the PRD and fixed them:

| # | Problem in the PRD | What I did |
|---|---|---|
| 1 | The table had **no UNIQUE constraint**, so `INSERT OR IGNORE` would never detect a duplicate and every re-import would double the data | Added `UNIQUE (transaction_id, event_date, action_type)` with `ON CONFLICT` |
| 2 | `amount REAL` (float) causes **rounding errors** with money | Stored as `amount_cents INTEGER`, parsed with `Decimal` |
| 3 | Python's `json.load` **reads the whole file into memory**, which breaks the streaming promise | Wrote a streaming JSON reader with `JSONDecoder.raw_decode` (still standard library only), plus JSON Lines support |
| 4 | Dates **without a timezone** had no rule | Rule: treat them as UTC (documented in `docs/date_formats.md`) |
| 5 | `--to 2026-03-31` becomes midnight, so `BETWEEN` **misses the rest of the last day** | Documented. The search code in week 2 will use `< next day` |
| 6 | Prefix search with `LIKE` **can't use the index** in SQLite, and `%` / `_` act as wildcards | Week 2 will use an index-friendly range query instead |

Also, `idx_tx_id` is not created separately, because the `UNIQUE` constraint's index already covers
`transaction_id` and a second index would only slow down imports.

---

## 8. Testing and quality

| Metric | Target (PRD) | Now |
|---|---|---|
| Automated tests | none given | **168 passing** |
| Test coverage | ≥ 85% | **97%** |
| 10,000-row import | < 3.0 s | **≈ 0.15 s** (checked by an automated test) |
| Unparameterized SQL | 0 | **0** (checked by an automated test) |
| Python versions | 3.10+ | Tested on 3.10 and 3.15 locally; CI runs 3.10–3.13 |

What the tests cover:
- **Dates:** about 25 accepted formats, timezone conversion, impossible dates rejected, the sort order being correct.
- **Amounts:** commas, currency symbols, `(12.50)` negatives, the float `0.1` stored correctly, `NaN` rejected.
- **Parsers:** Excel byte-order mark, quoted commas, extra columns, broken JSON lines, Fineract wrapped JSON,
  JSON records split across read chunks.
- **Storage:** skip vs update, duplicates inside one file, rollback on error, SQL-injection text stored as plain data.
- **Extreme input never crashes the import:** an amount of `1e30` (too big for SQLite), a year of
  10²⁰, a date of `0` (a placeholder, not 1 January 1970), a 200 KB CSV field and a non-UTF-8 file
  are all rejected with a clear message instead of a Python traceback.
- **End to end:** the real CLI, error messages without tracebacks, the 10,000-row speed test.

---

## 9. Demo script (2 minutes)

```bash
source .venv/bin/activate

# 1. Import messy sample data
audit-search import --file data/samples/audit_sample.csv

# 2. Import it again: everything is detected as a duplicate, nothing is doubled
audit-search import --file data/samples/audit_sample.csv

# 3. Look inside the database: all dates are in one UTC format
sqlite3 -header -column audit.db \
  "SELECT transaction_id, event_date, action_type, amount_cents FROM audit_events ORDER BY event_date LIMIT 5;"

# 4. Prove the ID index is used
sqlite3 audit.db "EXPLAIN QUERY PLAN SELECT * FROM audit_events WHERE transaction_id = 'TX-000010';"

# 5. Run the tests
pytest --cov
```

---

## 10. Status and plan

**Week 1 (done): the import half.** Project setup, CI, data model, CSV/JSON/JSONL parsers,
validation, date and amount normalization, SQLite storage with indexes, batching, the duplicate
policy, the `import` command, a synthetic data generator, 168 tests.

**Week 2: the search half.**
1. `search/queries.py`: exact ID, prefix and inclusive date range (index-friendly)
2. `export/`: aligned terminal table and CSV export with stable headers
3. Connect the `find` / `range` / `--export` commands
4. Interactive `menu`
5. `scripts/benchmark.py` to prove search takes under 50 ms
6. `data_privacy.md`, `CONTRIBUTING.md`, `LICENSE`

**Later (stretch goals):** a Flask dashboard on `127.0.0.1:5000`, extra filters, batch folder
import, import provenance (file hash).

---

## 11. Questions the mentor might ask

**Q: Why SQLite and not MySQL or PostgreSQL?**
They need a running server, a setup and passwords. This is a single-user, offline tool. SQLite
is one file and needs zero setup, and it still has B-tree indexes, transactions and
parameterized queries. If the project ever needs multiple users, only `storage/` and `search/`
would change.

**Q: Why not pandas?**
pandas loads the whole file into memory and is a large dependency. I only need to read rows one by
one, and the built-in `csv` module does that.

**Q: How do you prevent SQL injection?**
Every query uses `?` placeholders, so values are sent separately from the SQL text and can never
change the query. A test reads the source code with Python's `ast` module and fails if any
`execute()` call builds SQL with an f-string, `+`, `%` or `.format()`. Another test stores the text
`TX-1'; DROP TABLE audit_events; --` and checks that the table still exists.

**Q: How do you stream a JSON file without loading it all?**
I read the file in 64 KB chunks and use `json.JSONDecoder.raw_decode`, which decodes one value and
tells me where it ended. I then skip the comma and decode the next record. If a record is cut off
at the edge of a chunk, I read the next chunk and try again. There's a test that uses a 7-byte chunk
size to force records to be split.

**Q: Why store money in cents?**
A float cannot represent `0.10` exactly, so sums and exports could be off by a fraction of a cent.
Integers are exact. `Decimal` is used while parsing, so `"1,234.56"` becomes exactly `123456`.

**Q: What counts as a duplicate?**
The same transaction ID, at the same second, with the same action. A loan with a disbursement and
a repayment has two different events, which are not duplicates. The same deposit exported in two
overlapping files is a duplicate, even if one file wrote the date as `14/03/2026 09:30:00` and the
other as `2026-03-14T15:00:00+05:30`, because both normalize to the same UTC value.

**Q: What happens with a broken row? With a broken file?**
A broken row is rejected, counted and listed with its line number, and the import continues.
A broken file (for example invalid JSON syntax in the middle of an array) stops with a clear
error message. Batches saved before that point stay saved, and re-running the import is safe
because duplicates are detected.

**Q: Why is `03/04/2026` the 3rd of April?**
Fineract and Mifos are used mostly in regions that write day first. Day-first and month-first
dates can't be told apart automatically, so I chose one rule and documented it.
