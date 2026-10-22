# Financial-Audit-Log-Search
Build a standalone, offline Python CLI that ingests CSV/JSON financial audit logs, normalizes dates and transaction fields, stores them in an indexed SQLite database via parameterized queries, supports fast lookup by transaction ID and date range, and exports filtered results to CSV with stable headers. Stretch: a localhost-only Flask web UI.
