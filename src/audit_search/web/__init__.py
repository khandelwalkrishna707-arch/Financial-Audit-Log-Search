"""Optional local web dashboard (stretch goal). Needs Flask: pip install ".[web]".

The server only ever binds to 127.0.0.1, so it cannot be reached from other machines.
The web code holds no SQL: it calls search.service.search and the export functions.
"""

from __future__ import annotations

import io
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

from flask import Flask, Response, render_template, request

from audit_search.export.csv_writer import write_rows
from audit_search.normalize.fields import cents_to_str
from audit_search.search.filters import Filters
from audit_search.search.service import search
from audit_search.storage.database import connect, database_overview

HOST = "127.0.0.1"
MAX_ROWS_SHOWN = 1000
_FIELDS = ("transaction_id", "start", "end", "account", "user", "action",
           "min_amount", "max_amount")


def create_app(db_path: str) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path

    def run_query(form):
        filters = Filters.from_text(form.get("account"), form.get("user"), form.get("action"),
                                    form.get("min_amount"), form.get("max_amount"))
        if not Path(app.config["DB_PATH"]).is_file():
            raise ValueError("database not found - run 'audit-search import' first")
        with closing(connect(app.config["DB_PATH"])) as conn:
            return search(
                conn,
                transaction_id=form.get("transaction_id"),
                prefix=form.get("prefix") == "on",
                start=form.get("start"),
                end=form.get("end"),
                filters=filters,
            )

    def overview():
        if not Path(app.config["DB_PATH"]).is_file():
            return None
        try:
            with closing(connect(app.config["DB_PATH"])) as conn:
                return database_overview(conn)
        except sqlite3.Error:
            return None

    @app.get("/")
    def index():
        form = {name: request.args.get(name, "").strip() for name in _FIELDS}
        form["prefix"] = request.args.get("prefix", "")
        results, error = None, None
        if any(form[name] for name in _FIELDS):
            try:
                results = run_query(form)
            except (ValueError, sqlite3.Error) as exc:
                error = str(exc)
        summary = _summarize(results) if results else None
        return render_template(
            "index.html",
            overview=overview(),
            summary=summary,
            form=form,
            results=results[:MAX_ROWS_SHOWN] if results else results,
            total=len(results) if results is not None else 0,
            max_rows=MAX_ROWS_SHOWN,
            error=error,
            query_string=request.query_string.decode(),
            money=money,
        )

    @app.get("/export.csv")
    def export_csv():
        form = dict(request.args)
        try:
            results = run_query(form)
        except (ValueError, sqlite3.Error) as exc:
            return Response(f"error: {exc}\n", status=400, mimetype="text/plain")
        buffer = io.StringIO()
        write_rows(results, buffer)
        return Response(
            buffer.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_export.csv"},
        )

    return app


def money(cents: int | None) -> str:
    """Display amount with thousands separators: 123456789 -> "1,234,567.89"; None -> ""."""
    text = cents_to_str(cents)
    if not text:
        return ""
    sign, digits = ("-", text[1:]) if text.startswith("-") else ("", text)
    whole, frac = digits.split(".")
    return f"{sign}{int(whole):,}.{frac}"


def _summarize(results) -> dict[str, object]:
    """Totals shown above the results table (computed from the rows, no extra SQL)."""
    amounts = [tx.amount_cents for tx in results if tx.amount_cents is not None]
    actions = Counter(tx.action_type or "UNKNOWN" for tx in results)
    return {
        "total_cents": sum(amounts),
        "accounts": len({tx.account_id for tx in results if tx.account_id}),
        "first": results[0].event_date if results else None,
        "last": max(tx.event_date for tx in results) if results else None,
        "actions": actions.most_common(),
        "max_action": max(actions.values()) if actions else 1,
    }
