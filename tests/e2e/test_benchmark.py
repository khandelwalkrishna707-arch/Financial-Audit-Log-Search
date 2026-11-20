"""scripts/benchmark.py runs and reports the PRD targets."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import benchmark  # noqa: E402


def test_benchmark_reports_all_targets(capsys):
    assert benchmark.main(["--rows", "2000", "--repeat", "5"]) == 0
    out = capsys.readouterr().out
    for line in ("import", "exact ID", "prefix (7 chars)", "1-month range", "full-year range"):
        assert line in out
    assert "FAIL" not in out
    assert "all targets met" in out


def test_benchmark_exit_code_1_when_a_target_is_missed(monkeypatch, capsys):
    monkeypatch.setattr(benchmark, "QUERY_TARGET_MS", 0.0)  # impossible target
    assert benchmark.main(["--rows", "500", "--repeat", "2"]) == 1
    assert "TARGET MISSED" in capsys.readouterr().out


def test_benchmark_rejects_bad_arguments():
    try:
        benchmark.main(["--rows", "0"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected argparse to exit")
