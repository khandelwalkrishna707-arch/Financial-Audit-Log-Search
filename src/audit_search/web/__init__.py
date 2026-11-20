"""Optional local web dashboard (stretch goal). Needs Flask: pip install ".[web]".

The server only ever binds to 127.0.0.1, so it cannot be reached from other machines.
The web code holds no SQL: it calls search.service.search and the export functions.
"""

from __future__ import annotations

import io
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, Response, abort, render_template, request
from werkzeug.utils import secure_filename

from audit_search.export.csv_writer import write_rows
from audit_search.importer import import_file
from audit_search.ingest import SUPPORTED_EXTENSIONS
from audit_search.normalize.fields import cents_to_str
from audit_search.search.filters import Filters
from audit_search.search.service import search
from audit_search.storage.database import connect, database_overview

HOST = "127.0.0.1"
MAX_ROWS_SHOWN = 1000
_FIELDS = ("transaction_id", "start", "end", "account", "user", "action",
           "min_amount", "max_amount")


# Synthetic sample files shipped in the repository (present in a source checkout only).
SAMPLES_DIR = Path(__file__).resolve().parents[3] / "data" / "samples"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024


def create_app(db_path: str, samples_dir: Path | None = SAMPLES_DIR) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

    def sample_files() -> list[Path]:
        if samples_dir is None or not samples_dir.is_dir():
            return []
        return sorted(p for p in samples_dir.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS)

    @app.before_request
    def same_origin_posts_only():
        """Block other websites from posting to this local server (a simple CSRF guard)."""
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if origin and urlsplit(origin).netloc != request.host:
                abort(403)

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

    def render(form=None, results=None, error=None, imports=None, import_error=None):
        form = form or {name: "" for name in (*_FIELDS, "prefix")}
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
            imports=imports,
            import_error=import_error,
            has_samples=bool(sample_files()),
            query_string=request.query_string.decode(),
            money=money,
        )

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
        return render(form, results, error)

    def run_imports(paths: list[tuple[Path, str]]):
        summaries, problem = [], None
        with closing(connect(app.config["DB_PATH"])) as conn:
            for path, shown_name in paths:
                try:
                    summary = import_file(conn, path)
                    summary.source_file = shown_name
                    summaries.append(summary)
                except UnicodeDecodeError:
                    problem = f"{shown_name} is not UTF-8 text. Re-save it as UTF-8 and try again."
                except (OSError, ValueError, sqlite3.Error) as exc:
                    problem = f"{shown_name}: {exc}"
        return summaries, problem

    @app.post("/import")
    def upload():
        uploaded = [f for f in request.files.getlist("files") if f and f.filename]
        if not uploaded:
            return render(import_error="Choose at least one CSV, JSON or JSONL file."), 400
        with tempfile.TemporaryDirectory(prefix="audit-search-") as tmp:
            paths = []
            for item in uploaded:
                name = secure_filename(item.filename) or "upload"
                if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
                    return render(import_error=f"{item.filename}: unsupported file type. "
                                  "Use .csv, .json, .jsonl or .ndjson."), 400
                target = Path(tmp) / name
                item.save(target)
                paths.append((target, name))
            summaries, problem = run_imports(paths)
        return render(imports=summaries, import_error=problem)

    @app.post("/import-samples")
    def import_samples():
        files = sample_files()
        if not files:
            return render(import_error="No sample files found."), 404
        summaries, problem = run_imports([(p, p.name) for p in files])
        return render(imports=summaries, import_error=problem)

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
