"""pytest entry for the eval harness: every seeded case must pass."""
import os
from pathlib import Path

os.environ.setdefault("MATCHBOOK_DB", str(Path(__file__).parent / "results" / "eval.db"))
os.environ["MATCHBOOK_PACE"] = "0"

from run_evals import run_all  # noqa: E402


def test_all_cases_pass():
    res = run_all()
    failed = {r["title"]: [k for k, v in r["checks"].items() if not v] for r in res["rows"] if not r["pass"]}
    assert not failed, failed
    assert res["metrics"]["false_dispute_rate"] == 0
