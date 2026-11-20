"""The optional Flask dashboard, through Flask's test client."""

import csv
import io

import pytest

pytest.importorskip("flask")

from audit_search import cli  # noqa: E402
from audit_search.web import HOST, create_app  # noqa: E402


@pytest.fixture
def client(tmp_path, fixtures_dir):
    db = tmp_path / "a.db"
    assert cli.main(["import", "--file", str(fixtures_dir / "valid.csv"), "--db", str(db)]) == 0
    return create_app(str(db)).test_client()


def test_host_is_localhost_only():
    assert HOST == "127.0.0.1"


def test_empty_form(client):
    page = client.get("/").get_data(as_text=True)
    assert "Audit log search" in page and "<table>" not in page


def test_search_by_id(client):
    page = client.get("/?transaction_id=TX-1002").get_data(as_text=True)
    assert "1 result" in page and "1000.50" in page and "WITHDRAWAL" in page


def test_prefix_range_and_filters(client):
    page = client.get("/?transaction_id=TX-100&prefix=on&action=deposit").get_data(as_text=True)
    assert "2 results" in page
    page = client.get("/?start=2026-03-14&end=2026-03-14&min_amount=5").get_data(as_text=True)
    assert "2 results" in page and "TX-1003" not in page


def test_no_results_and_errors(client):
    assert "No results." in client.get("/?transaction_id=NOPE").get_data(as_text=True)
    page = client.get("/?start=2026-03-15&end=2026-03-01").get_data(as_text=True)
    assert "Error:" in page and "after end date" in page


def test_html_is_escaped(client):
    page = client.get("/?transaction_id=<script>x</script>").get_data(as_text=True)
    assert "<script>x" not in page


def test_export_csv(client):
    response = client.get("/export.csv?start=2026-03-01&end=2026-03-31")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
    assert [r["transaction_id"] for r in rows] == ["TX-1001", "TX-1002", "TX-1003", "TX-1004"]


def test_export_bad_input(client):
    response = client.get("/export.csv")
    assert response.status_code == 400


def test_missing_database(tmp_path):
    page = create_app(str(tmp_path / "none.db")).test_client().get("/?transaction_id=X")
    assert "database not found" in page.get_data(as_text=True)


def test_web_command_runs_on_localhost(tmp_path, monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr("flask.Flask.run", lambda self, **kw: seen.update(kw))
    assert cli.main(["web", "--db", str(tmp_path / "a.db"), "--port", "5055"]) == 0
    assert seen == {"host": "127.0.0.1", "port": 5055, "debug": False}
    assert "http://127.0.0.1:5055" in capsys.readouterr().out


def test_web_command_without_flask(tmp_path, monkeypatch, capsys):
    import builtins
    real_import = builtins.__import__

    def no_web(name, *args, **kwargs):
        if name == "audit_search.web":
            raise ImportError("no flask")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", no_web)
    assert cli.main(["web", "--db", str(tmp_path / "a.db")]) == 1
    assert "needs Flask" in capsys.readouterr().err
