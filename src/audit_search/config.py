"""Project-wide settings in one place, so no magic numbers are scattered around the code."""

import os

# Where the SQLite database lives unless --db is given. Can be overridden with an env variable.
DEFAULT_DB_PATH = os.environ.get("AUDIT_SEARCH_DB", "audit.db")

# How many rows are written to SQLite in one transaction (PRD: 1,000-row batches).
BATCH_SIZE = 1000

# What to do when a record that is already stored is imported again.
DUPLICATE_POLICIES = ("skip", "update")
DEFAULT_DUPLICATE_POLICY = "skip"

# How many rejected-row reasons to keep in memory for the import summary.
# All rejected rows are still COUNTED; only the details list is capped.
MAX_REJECTIONS_KEPT = 1000
