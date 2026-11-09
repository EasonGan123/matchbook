"""Load fixtures/seed.json into SQLite. `python -m db.seed` resets the demo."""
from __future__ import annotations

import json

from db.conn import ROOT, insert, now_iso, reset_db, tx

SEED = ROOT / "fixtures" / "seed.json"
SCENARIOS = ROOT / "fixtures" / "scenarios.json"
EXTRACTED = ROOT / "fixtures" / "extracted"


def load_seed() -> dict:
    return json.loads(SEED.read_text())


def load_scenarios() -> list[dict]:
    return json.loads(SCENARIOS.read_text())["scenarios"]


def contract_terms(contract_id: str, fallback: dict) -> dict:
    """Terms come from the extraction cache (fixtures/extracted). If no cache exists yet,
    fall back to the fixture's ground truth, marked as such."""
    cached = EXTRACTED / f"{contract_id}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    return {**fallback, "_source": "fixture-ground-truth"}


def seed() -> None:
    reset_db()
    data = load_seed()
    ts = now_iso()
    with tx() as c:
        for v in data["vendors"]:
            insert(c, "vendors", {k: v.get(k) for k in ("id", "name", "contact_name", "contact_email", "payment_terms")}
                   | {"stats_json": json.dumps(v.get("stats", {}))})
        for po in data["purchase_orders"]:
            insert(c, "purchase_orders", {k: po.get(k) for k in
                   ("id", "vendor_id", "number", "issued_on", "buyer_name", "buyer_email", "department", "memo")})
            for ln in po["lines"]:
                insert(c, "po_lines", {**ln, "po_id": po["id"]})
        for r in data["item_receipts"]:
            insert(c, "item_receipts", r)
        for k in data["contracts"]:
            ground = {f: k[f] for f in ("id", "title", "vendor_id", "effective_start", "effective_end",
                                         "payment_terms", "price_schedule", "clauses")}
            terms = contract_terms(k["id"], ground)
            insert(c, "contracts", {"id": k["id"], "vendor_id": k["vendor_id"], "title": k["title"],
                                    "pdf_path": f"pdf/{k['id']}.pdf", "effective_start": k["effective_start"],
                                    "effective_end": k["effective_end"], "terms_json": json.dumps(terms)})
        for b in data["bills"]:
            amount = sum(ln["quantity"] * ln["unit_price_cents"] for ln in b["lines"])
            insert(c, "bills", {
                "id": b["id"], "vendor_id": b["vendor_id"], "po_id": b.get("po_id"),
                "invoice_number": b["invoice_number"], "invoice_date": b["invoice_date"],
                "due_date": b.get("due_date"), "amount_cents": amount, "status": b["status"],
                "match_status": b["match_status"], "ramp_flag": b.get("ramp_flag"),
                "pdf_path": f"pdf/{b['id']}.pdf", "vendor_notes": b.get("vendor_notes"),
                "supersedes": None, "paid_on": b.get("paid_on"), "created_at": ts})
            for ln in b["lines"]:
                insert(c, "bill_lines", {**ln, "bill_id": b["id"],
                                         "amount_cents": ln["quantity"] * ln["unit_price_cents"]})


if __name__ == "__main__":
    seed()
    print("Seeded matchbook.db")
