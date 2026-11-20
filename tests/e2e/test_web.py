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
    assert "Audit Log Search" in page and "<table>" not in page and "Start a search" in page


def test_search_by_id(client):
    page = client.get("/?transaction_id=TX-1002").get_data(as_text=True)
    assert "1 event<" in page and "1,000.50" in page and "WITHDRAWAL" in page


def test_prefix_range_and_filters(client):
    page = client.get("/?transaction_id=TX-100&prefix=on&action=deposit").get_data(as_text=True)
    assert "2 events<" in page
    page = client.get("/?start=2026-03-14&end=2026-03-14&min_amount=5").get_data(as_text=True)
    assert "2 events<" in page and "TX-1003" not in page
    assert "Total amount" in page and "2,250.50" in page and "Events by action" in page


def test_no_results_and_errors(client):
    assert "No events match" in client.get("/?transaction_id=NOPE").get_data(as_text=True)
    page = client.get("/?start=2026-03-15&end=2026-03-01").get_data(as_text=True)
    assert 'role="alert"' in page and "after end date" in page


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
    opened = []
    monkeypatch.setattr("flask.Flask.run", lambda self, **kw: seen.update(kw))
    monkeypatch.setattr("webbrowser.open", opened.append)
    monkeypatch.setattr("threading.Timer", lambda delay, fn, args: type(
        "T", (), {"start": lambda self: fn(*args)})())
    assert cli.main(["web", "--db", str(tmp_path / "a.db"), "--port", "5055", "--open"]) == 0
    assert seen == {"host": "127.0.0.1", "port": 5055, "debug": False}
    assert opened == ["http://127.0.0.1:5055"]
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


def test_overview_cards(client):
    page = client.get("/").get_data(as_text=True)
    assert "Records indexed" in page and ">4<" in page and "2026-03-14" in page


def test_money_display():
    from audit_search.web import money
    assert money(123456789) == "1,234,567.89"
    assert money(-5) == "-0.05"
    assert money(None) == ""


def test_upload_import(tmp_path, fixtures_dir):
    db = tmp_path / "fresh.db"
    client = create_app(str(db), samples_dir=None).test_client()
    assert "No data yet" in client.get("/").get_data(as_text=True)
    with (fixtures_dir / "corrupted.csv").open("rb") as one, \
            (fixtures_dir / "valid.json").open("rb") as two:
        page = client.post("/import", data={"files": [(one, "corrupted.csv"),
                                                      (two, "valid.json")]},
                           content_type="multipart/form-data").get_data(as_text=True)
    assert "Import finished" in page and "corrupted.csv" in page and "valid.json" in page
    assert "line 3: missing transaction_id" in page
    assert "Load sample data" not in page
    page = client.get("/?transaction_id=TX-2001").get_data(as_text=True)
    assert "1 event<" in page


def test_upload_errors(tmp_path):
    client = create_app(str(tmp_path / "a.db"), samples_dir=None).test_client()
    assert client.post("/import", data={}).status_code == 400
    response = client.post("/import", data={"files": (io.BytesIO(b"x"), "log.xml")},
                           content_type="multipart/form-data")
    assert response.status_code == 400 and "unsupported file type" in response.get_data(True)
    page = client.post("/import", data={"files": (io.BytesIO("a,b\n\xe9".encode("latin-1")),
                                                  "bad.csv")},
                       content_type="multipart/form-data").get_data(as_text=True)
    assert "not UTF-8" in page
    page = client.post("/import", data={"files": (io.BytesIO(b"[{"), "broken.json")},
                       content_type="multipart/form-data").get_data(as_text=True)
    assert "broken.json:" in page
    assert client.post("/import-samples").status_code == 404


def test_load_sample_data(tmp_path, fixtures_dir):
    samples = tmp_path / "samples"
    samples.mkdir()
    (samples / "valid.csv").write_bytes((fixtures_dir / "valid.csv").read_bytes())
    (samples / "notes.txt").write_text("ignored")
    client = create_app(str(tmp_path / "a.db"), samples_dir=samples).test_client()
    assert "Load sample data" in client.get("/").get_data(as_text=True)
    page = client.post("/import-samples").get_data(as_text=True)
    assert "Import finished" in page and "notes.txt" not in page
    assert "Records indexed" in page and ">4<" in page


def test_other_websites_cannot_post(tmp_path):
    client = create_app(str(tmp_path / "a.db"), samples_dir=None).test_client()
    assert client.post("/import-samples", headers={"Origin": "https://evil.example"}
                       ).status_code == 403
    assert client.post("/import-samples", headers={"Origin": "http://localhost"}
                       ).status_code == 404  # same host passes the guard
