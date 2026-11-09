"""Eval harness: runs the nine seeded cases end to end and prints a scorecard.

    make eval            (from the repo root)

Uses its own database file so it never disturbs the demo. Results go to
evals/results/latest.json, which the /evals page reads. The `mode` field says
whether Claude was live or responses were replayed; only live or recorded runs
measure the model.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ.setdefault("MATCHBOOK_DB", str(HERE / "results" / "eval.db"))
os.environ.setdefault("MATCHBOOK_PACE", "0")
sys.path.insert(0, str(HERE.parent / "backend"))

from agent.llm import MODEL, RECORDED, mode  # noqa: E402
from db.conn import loads  # noqa: E402
from db.seed import load_scenarios, seed  # noqa: E402
from engine.money import usd  # noqa: E402
from orchestrator import service  # noqa: E402

DISPUTE_PLAYBOOKS = {"credit_memo_request", "corrected_bill_request", "reject_duplicate"}


def _secs(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    return round((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds(), 2)


def run_all() -> dict:
    seed()
    service.ingest()
    rows = []
    for sc in load_scenarios():
        exp = sc["expect"]
        cid = service.case_id_for(sc["bill_id"])
        t0 = time.time()
        service.run_case(cid)
        case = service.get_case(cid)
        dx = loads(case["diagnosis_json"], {}) or {}
        detail = service.case_detail(cid)
        draft = detail["draft"]
        cited = set(dx.get("evidence_ids") or [])
        checks = {
            "root_cause": case["root_cause"] == exp["root_cause"],
            "playbook": case["playbook"] == exp["playbook"],
            "amount": case["variance_cents"] == exp["amount_cents"],
            "citations": set(exp["must_cite"]) <= cited,
            "state": case["state"] == exp["state_after_run"],
        }
        if draft:
            checks["draft_validated"] = bool(draft["validation"].get("ok"))
            if exp["is_dispute"] and exp["playbook"] != "reject_duplicate":
                checks["draft_amount_exact"] = draft["variables"].get("variance_total") == usd(exp["amount_cents"])
        if exp.get("injection_flagged"):
            checks["injection_flagged"] = bool(dx.get("injection_flagged")) and any(
                e["kind"] == "security" for e in detail["events"])
        drafted_dispute = case["playbook"] in DISPUTE_PLAYBOOKS and case["state"] == "PENDING_APPROVAL"

        # Close the loop: approve, then fast-forward the follow-up until the case settles.
        final = case["state"]
        if case["state"] == "PENDING_APPROVAL":
            service.approve(cid, "Eval harness")
            if service.get_case(cid)["state"] == "AWAITING_VENDOR":
                service.fast_forward(cid)
            final = service.get_case(cid)["state"]
            checks["closed_loop"] = final == "SYNCED"
        case = service.get_case(cid)
        rows.append({
            "n": sc["n"], "key": sc["key"], "title": sc["title"], "setup": sc["setup"], "case_id": cid,
            "expected": exp, "got": {"root_cause": case["root_cause"], "playbook": case["playbook"],
                                     "amount_cents": case["variance_cents"], "state_after_run": final,
                                     "cited": sorted(cited)},
            "checks": checks, "pass": all(checks.values()), "drafted_dispute": drafted_dispute,
            "seconds_to_draft": _secs(case["started_at"], case["drafted_at"]),
            "tokens_in": case["tokens_in"], "tokens_out": case["tokens_out"],
            "wall_seconds": round(time.time() - t0, 2),
        })

    n = len(rows)
    non_dispute = [r for r in rows if not r["expected"]["is_dispute"]]
    drafted = [r for r in rows if r["seconds_to_draft"] is not None]
    amount_rows = [r for r in rows if "draft_amount_exact" in r["checks"]]
    m = mode()
    replay_kind = "recorded" if RECORDED.exists() and any(RECORDED.iterdir()) else "scripted"
    result = {
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "live" if m == "live" else f"replay-{replay_kind}",
        "model": MODEL if m == "live" or replay_kind == "recorded" else None,
        "metrics": {
            "cases_passed": sum(r["pass"] for r in rows), "cases": n,
            "root_cause_accuracy": round(sum(r["checks"]["root_cause"] for r in rows) / n, 3),
            "amount_exact_match": round(sum(r["checks"]["draft_amount_exact"] for r in amount_rows) / len(amount_rows), 3)
            if amount_rows else None,
            "false_dispute_rate": round(sum(r["drafted_dispute"] for r in non_dispute) / len(non_dispute), 3),
            "median_seconds_to_draft": sorted(r["seconds_to_draft"] for r in drafted)[len(drafted) // 2]
            if drafted else None,
            "tokens_per_case": round(sum(r["tokens_in"] + r["tokens_out"] for r in rows) / n) if m == "live" else None,
        },
        "rows": rows,
    }
    out = HERE / "results" / "latest.json"
    out.write_text(json.dumps(result, indent=1, default=str))
    return result


def print_scorecard(res: dict) -> None:
    m = res["metrics"]
    print(f"\nMATCHBOOK EVAL  ·  mode: {res['mode']}  ·  model: {res['model'] or 'n/a (scripted responses)'}")
    print("─" * 78)
    for r in res["rows"]:
        mark = "PASS" if r["pass"] else "FAIL"
        failed = [k for k, v in r["checks"].items() if not v]
        print(f" {r['n']}  {mark}  {r['title']:<24} {r['got']['root_cause'] or '-':<22} "
              f"{usd(r['got']['amount_cents'] or 0):>11}  {r['got']['state_after_run']:<10}"
              + (f"  ✗ {', '.join(failed)}" if failed else ""))
    print("─" * 78)
    print(f" passed {m['cases_passed']}/{m['cases']}   root cause {m['root_cause_accuracy']:.0%}   "
          f"amounts exact {m['amount_exact_match']:.0%}   false disputes {m['false_dispute_rate']:.0%}   "
          f"tokens/case {m['tokens_per_case'] if m['tokens_per_case'] is not None else 'n/a'}")
    if res["mode"] == "replay-scripted":
        print(" note: scripted model responses; this checks the pipeline and guardrails, not Claude.")


if __name__ == "__main__":
    res = run_all()
    print_scorecard(res)
    sys.exit(0 if res["metrics"]["cases_passed"] == res["metrics"]["cases"] else 1)
