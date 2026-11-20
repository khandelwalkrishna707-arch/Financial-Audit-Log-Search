# Contributing

Thanks for helping! This guide gets you from clone to pull request.

## Setup

Requires Python 3.10 or newer.

```bash
git clone https://github.com/khandelwalkrishna707-arch/Financial-Audit-Log-Search.git
cd Financial-Audit-Log-Search
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e . -r requirements-dev.txt
pytest                               # everything should pass before you start
```

## Workflow

1. **Open (or pick) an issue** that describes one feature or bug.
2. **Create a branch from `main`** named after the issue:
   `feature/<issue-number>-short-name` or `fix/<issue-number>-short-name`,
   e.g. `feature/4-csv-export`.
3. **Write the code and its tests together**, in small, focused commits.
4. **Check before pushing**:
   ```bash
   ruff check .
   pytest --cov            # fails below 85% coverage
   ```
5. **Push and open a pull request** whose description says `Closes #<issue-number>`.
   GitHub Actions runs lint and tests on Python 3.10–3.13. The PR is merged after the
   checks pass and a mentor approves.
6. After merging, delete the branch and `git pull` `main` before starting the next task.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<area>): <what changed, in the imperative>

feat(search): add prefix search
fix(normalize): accept dates with a +0530 offset
docs: explain the duplicate policy
test(ingest): cover CSV rows with extra columns
chore: update CI to Python 3.13
```

Keep the first line under 72 characters. Explain *why* in the body when it isn't obvious.

## Code rules

- **Respect the layers.** `ingest/` reads files, `normalize/` cleans values, `storage/` writes
  to SQLite, `search/` reads from it, `export/` formats output, and `cli.py` only calls them.
  A layer talks only to the one next to it.
- **Parameterized SQL only.** Use `?` placeholders and constant SQL strings, never f-strings,
  `+`, `%` or `.format()`. `tests/unit/test_sql_safety.py` fails the build otherwise.
- **Dates are ISO 8601 UTC text, money is integer cents.** Convert at the edges with
  `normalize_date()` and `parse_amount_cents()` / `cents_to_str()`.
- **Never crash on bad data.** Reject the row with a clear reason, or stop the file with an
  `error: ...` message, never a traceback.
- **Standard library first.** Adding a third-party package needs a good reason in the PR.
- **Python 3.10 compatible.** CI tests 3.10–3.13.

## Tests

| Folder | What goes there |
|---|---|
| `tests/unit/` | One module at a time, using the in-memory `conn` fixture from `conftest.py` |
| `tests/integration/` | Whole import path: file in, database checked |
| `tests/e2e/` | The real CLI and scripts, including the performance targets |
| `tests/fixtures/` | Small hand-written valid and corrupted files |

Check performance after changes to storage or search:

```bash
python scripts/benchmark.py          # PRD targets: import < 3 s, queries < 50 ms
```

## Data

Only synthetic data goes into the repository. Never commit real audit logs, databases or
exports, and never paste real records into issues or PRs. See
[docs/data_privacy.md](docs/data_privacy.md).
