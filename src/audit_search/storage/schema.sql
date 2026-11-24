-- One table holds every cleaned audit event.
CREATE TABLE IF NOT EXISTS audit_events (
    id             INTEGER PRIMARY KEY,
    transaction_id TEXT    NOT NULL,
    event_date     TEXT    NOT NULL,            -- ISO 8601 UTC, e.g. 2026-03-14T09:30:00Z
    account_id     TEXT,
    action_type    TEXT    NOT NULL DEFAULT '', -- e.g. DEPOSIT, WITHDRAWAL; '' when unknown
    amount_cents   INTEGER,                     -- money in whole cents: 12.50 is stored as 1250
    user_id        TEXT,
    source_file    TEXT,

    -- Duplicate rule: the same transaction, at the same moment, doing the same action,
    -- is the same audit event.
    UNIQUE (transaction_id, event_date, action_type)
);

-- B-tree index for date-range searches. ISO UTC text sorts in time order.
CREATE INDEX IF NOT EXISTS idx_tx_date ON audit_events (event_date);

-- B-tree index for transaction-ID searches (exact `= ?` and prefix `LIKE ?`).
-- The search queries name it with INDEXED BY, so they always use it (issue #4).
CREATE INDEX IF NOT EXISTS idx_tx_id ON audit_events (transaction_id);
