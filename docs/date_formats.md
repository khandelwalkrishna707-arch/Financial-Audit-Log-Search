# Accepted date formats and timezone rules

Every date is converted **once, at import time** to ISO 8601 UTC with second precision:

```
YYYY-MM-DDTHH:MM:SSZ      e.g. 2026-03-14T09:30:00Z
```

Because every stored date has this exact fixed-width format, sorting the text alphabetically
gives the same order as sorting by time. That lets SQLite answer date-range searches with a
normal B-tree index (`idx_tx_date`).

Code: [`src/audit_search/normalize/dates.py`](../src/audit_search/normalize/dates.py)

## Rules

1. **With a timezone** (`Z`, `+05:30`, `-0500`) → converted to UTC.
   `2026-03-14T15:00:00+05:30` → `2026-03-14T09:30:00Z`
2. **Without a timezone** → assumed to already be UTC.
   `2026-03-14 09:30:00` → `2026-03-14T09:30:00Z`
3. **Slash and dash dates are DAY first.** `03/04/2026` is 3 April 2026, not March 4.
   US-style month-first dates are not supported, because they can't be told apart from day-first.
4. **Date only** → midnight UTC. `2026-03-14` → `2026-03-14T00:00:00Z`
5. **Fractional seconds are dropped.** `09:30:00.750Z` → `09:30:00Z`
6. **Numbers are Unix timestamps** (seconds, or milliseconds when very large), except
   **8-digit numbers, which are `YYYYMMDD`**: `20260314` → 14 March 2026. Timestamps before
   March 1973 (such as `0`) are rejected, because in an audit log they are almost always a
   placeholder for "no date", not a real 1970 date.
7. Anything else is **rejected** with the reason `bad event_date: ...`. Impossible dates such as
   `31/02/2026` are rejected, never "corrected".

## Accepted inputs

| Example | Kind |
|---|---|
| `2026-03-14T09:30:00Z`, `2026-03-14T09:30:00.123Z` | ISO 8601, UTC |
| `2026-03-14T15:00:00+05:30`, `2026-03-14T15:00:00+0530` | ISO 8601 with offset |
| `2026-03-14 09:30:00`, `2026-03-14 09:30`, `2026-03-14` | ISO without timezone |
| `14/03/2026 09:30:00`, `14/03/2026 09:30`, `14/03/2026` | day/month/year |
| `14-03-2026 09:30:00`, `14-03-2026` | day-month-year |
| `2026/03/14 09:30:00`, `2026/03/14`, `20260314` | year first |
| `14 March 2026`, `14 Mar 2026` (optionally `+ HH:MM:SS`) | written month (Apache Fineract default) |
| `1773480600`, `1773480600000` | Unix epoch seconds / milliseconds |
| `[2026, 3, 14]`, `[2026, 3, 14, 9, 30, 0]` | JSON date list (Apache Fineract API) |

## Searching (week 2)

Search dates go through the **same** `normalize_date` function, so a search for `14/03/2026` and a
stored `2026-03-14T00:00:00Z` always match. An end date given without a time (`--to 2026-03-31`)
must include the **whole** day. See [remaining_work.md](remaining_work.md).
