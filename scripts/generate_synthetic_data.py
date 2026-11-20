"""Generate FAKE audit logs for demos, tests and benchmarks. No real customer data, ever.

The output is deliberately messy, like real exports:
  * dates in 6 different formats and timezones,
  * about 2% duplicates (the same event repeated, often with its date written differently),
  * about 2% broken rows (missing ID, impossible date, bad amount).

Usage:
    python scripts/generate_synthetic_data.py --rows 10000 --out data/generated/audit_10k.csv
    python scripts/generate_synthetic_data.py --rows 500 --format jsonl --out data/generated/a.jsonl
    python scripts/generate_synthetic_data.py --samples   # rewrites the files in data/samples/
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

FIELDS = ("transaction_id", "event_date", "account_id", "action_type", "amount", "user_id")
ACTIONS = ("DEPOSIT", "WITHDRAWAL", "DISBURSEMENT", "REPAYMENT", "TRANSFER", "FEE_CHARGE")
IST = timezone(timedelta(hours=5, minutes=30))
START = datetime(2026, 1, 1, tzinfo=timezone.utc)
SPAN_SECONDS = 365 * 24 * 3600

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


def format_date(moment: datetime, style: int) -> str:
    """Write the same moment in one of several real-world formats."""
    if style == 0:
        return moment.strftime("%Y-%m-%dT%H:%M:%SZ")  # ISO, UTC
    if style == 1:
        return moment.astimezone(IST).isoformat()  # ISO with +05:30 offset
    if style == 2:
        return moment.strftime("%Y-%m-%d %H:%M:%S")  # no timezone (treated as UTC)
    if style == 3:
        return moment.strftime("%d/%m/%Y %H:%M:%S")  # day-first
    if style == 4:
        return str(int(moment.timestamp()))  # Unix epoch seconds
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")  # ISO with milliseconds


def make_rows(count: int, seed: int) -> list[dict[str, str]]:
    rng = random.Random(seed)  # fixed seed -> same file every time
    rows: list[dict[str, str]] = []
    serial = 0
    while len(rows) < count:
        roll = rng.random()

        if rows and roll < 0.02:  # duplicate of an earlier event, date written differently
            original = dict(rng.choice(rows[-50:]))
            moment = original.pop("_moment", None)
            if moment is not None:
                original["event_date"] = format_date(moment, rng.randrange(6))
            rows.append(original)
            continue

        serial += 1
        # Second-level precision, like real audit logs.
        moment = START + timedelta(seconds=rng.randrange(SPAN_SECONDS))
        row = {
            "transaction_id": f"TX-{serial:06d}",
            "event_date": format_date(moment, rng.randrange(6)),
            "account_id": f"AC-{rng.randrange(1000, 9999)}",
            "action_type": rng.choice(ACTIONS),
            "amount": f"{rng.randrange(100, 5_000_000) / 100:.2f}",
            "user_id": f"user{rng.randrange(1, 40):02d}",
            "_moment": moment,
        }

        if roll < 0.03:
            row["transaction_id"] = ""  # broken: missing ID
        elif roll < 0.035:
            row["event_date"] = "31/02/2026"  # broken: impossible date
        elif roll < 0.04:
            row["amount"] = "12.3.4"  # broken: not a number
        rows.append(row)

    for row in rows:
        row.pop("_moment", None)
    return rows


def write(rows: list[dict[str, str]], path: Path, fmt: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    elif fmt == "json":
        path.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    elif fmt == "jsonl":
        with open(path, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")
    else:
        raise ValueError(f"unknown format {fmt!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--format", choices=("csv", "json", "jsonl"), default="csv")
    parser.add_argument("--out", type=Path, default=Path("data/generated/audit_10k.csv"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--samples", action="store_true", help="regenerate data/samples/")
    args = parser.parse_args()

    if args.samples:
        write(make_rows(500, seed=1), SAMPLES_DIR / "audit_sample.csv", "csv")
        write(make_rows(200, seed=2), SAMPLES_DIR / "audit_sample.json", "json")
        write(make_rows(200, seed=3), SAMPLES_DIR / "audit_sample.jsonl", "jsonl")
        print(f"Sample files written to {SAMPLES_DIR}")
        return

    write(make_rows(args.rows, args.seed), args.out, args.format)
    print(f"Wrote {args.rows} rows to {args.out}")


if __name__ == "__main__":
    main()
