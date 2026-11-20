# Data privacy guide

Audit logs contain sensitive financial data: account numbers, amounts, user IDs and the
history of who did what. This guide explains how the tool handles that data, and what
**you** must do to keep it safe.

## What the tool does

| | |
|---|---|
| **Runs offline** | The tool never opens a network connection. It uses only the Python standard library, and nothing is uploaded, synced or sent anywhere. |
| **One local file** | Imported records are stored in one SQLite file: `audit.db` in the current folder by default, or the path you give with `--db` / `AUDIT_SEARCH_DB`. |
| **Only what is imported** | Each record keeps: transaction ID, event date, account ID, action type, amount, user ID and the source **file name** (not its path). Other columns in the input file are ignored and not stored. |
| **No telemetry** | No usage statistics, crash reports or logs are sent or written anywhere. |
| **Web UI (stretch goal)** | If built, it must listen on `127.0.0.1` only, so other computers on the network cannot reach it. |

## What the tool does NOT do

- **It does not encrypt** the database. `audit.db` is a normal file: anyone who can read it
  can read every record.
- **It does not anonymize or mask** data. Searches and CSV exports contain the real values.
- **It does not delete** source files or exports for you.

## Your responsibilities

1. **Never commit real data to Git.** `.gitignore` already blocks `*.db`, `*.sqlite3`,
   `exports/` and `data/generated/`. Only the synthetic files in `data/samples/` belong in the
   repository. Check `git status` before every commit.
2. **Use synthetic data for demos, tests and bug reports.** Generate it with
   `python scripts/generate_synthetic_data.py`. Never paste real records into a GitHub
   issue or pull request.
3. **Protect the files on disk.**
   - Turn on full-disk encryption (FileVault on macOS, BitLocker on Windows).
   - Restrict the database to your user: `chmod 600 audit.db`.
4. **Treat CSV exports like the original logs.** Share them only through channels your
   organisation approves, and delete them when the review is finished.
5. **Clean up when you are done**, especially on a shared computer:
   ```bash
   rm audit.db            # the database
   rm -r exports/         # any CSV exports
   gh auth logout         # if you logged in to GitHub on a shared machine
   ```
6. **Report a privacy problem privately.** If you find a bug that could leak data, tell the
   maintainer directly. Don't describe it with real data in a public issue.

## Scope reminder

The tool indexes and retrieves audit records. It does not validate financial correctness,
reconcile ledgers or replace an official audit sign-off.
