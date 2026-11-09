"""Mock Ramp Bill Pay, backed by SQLite."""
from __future__ import annotations

import json
import uuid

from db.conn import insert, loads, now_iso, query, query_one, tx, update


def _bill(row: dict | None) -> dict | None:
    if not row:
        return None
    row = dict(row)
    row["lines"] = query("SELECT * FROM bill_lines WHERE bill_id = ? ORDER BY line_no", (row["id"],))
    row["vendor"] = query_one("SELECT id, name, contact_email FROM vendors WHERE id = ?", (row["vendor_id"],))
    return row


class MockRampClient:
    # ---- read ----
    def list_bills(self, status: str | None = None) -> list[dict]:
        if status:
            rows = query("SELECT * FROM bills WHERE status = ? ORDER BY invoice_date", (status,))
        else:
            rows = query("SELECT * FROM bills ORDER BY invoice_date")
        return [_bill(r) for r in rows]

    def get_bill(self, bill_id: str) -> dict | None:
        return _bill(query_one("SELECT * FROM bills WHERE id = ?", (bill_id,)))

    def get_purchase_order(self, po_id: str) -> dict | None:
        po = query_one("SELECT * FROM purchase_orders WHERE id = ?", (po_id,))
        if po:
            po["lines"] = query("SELECT * FROM po_lines WHERE po_id = ? ORDER BY line_no", (po_id,))
        return po

    def list_item_receipts(self, po_id: str) -> list[dict]:
        return query("SELECT * FROM item_receipts WHERE po_id = ? ORDER BY received_on", (po_id,))

    def get_vendor(self, vendor_id: str) -> dict | None:
        v = query_one("SELECT * FROM vendors WHERE id = ?", (vendor_id,))
        if v:
            v["stats"] = loads(v.pop("stats_json"), {})
        return v

    def list_contracts(self, vendor_id: str) -> list[dict]:
        rows = query("SELECT * FROM contracts WHERE vendor_id = ? ORDER BY effective_start", (vendor_id,))
        for r in rows:
            r["terms"] = loads(r.pop("terms_json"), {})
        return rows

    def list_vendor_bills(self, vendor_id: str) -> list[dict]:
        return [_bill(r) for r in query(
            "SELECT * FROM bills WHERE vendor_id = ? ORDER BY invoice_date", (vendor_id,))]

    # ---- write ----
    def create_approval_request(self, bill_id: str, payload: dict) -> dict:
        row = {"id": f"APR-{uuid.uuid4().hex[:6].upper()}", "case_id": payload["case_id"],
               "draft_id": payload.get("draft_id"), "bill_id": bill_id, "status": "pending",
               "approver": payload.get("approver", "Controller"), "requested_at": now_iso(),
               "decided_at": None, "note": payload.get("note")}
        with tx() as c:
            insert(c, "approvals", row)
        return row

    def update_bill(self, bill_id: str, patch: dict) -> dict:
        allowed = {"status", "match_status", "supersedes", "ramp_flag"}
        bad = set(patch) - allowed
        if bad:
            raise ValueError(f"fields not writable: {bad}")
        with tx() as c:
            update(c, "bills", bill_id, patch)
        return self.get_bill(bill_id)

    def create_bill(self, bill: dict) -> dict:
        bill_id = bill.get("id") or f"B-{uuid.uuid4().hex[:6].upper()}"
        lines = bill.pop("lines")
        amount = sum(ln["quantity"] * ln["unit_price_cents"] for ln in lines)
        with tx() as c:
            insert(c, "bills", {**bill, "id": bill_id, "amount_cents": amount, "created_at": now_iso()})
            for i, ln in enumerate(lines, 1):
                insert(c, "bill_lines", {"id": f"{bill_id}-L{i}", "bill_id": bill_id, "line_no": i,
                                         "po_line_id": ln.get("po_line_id"), "sku": ln["sku"],
                                         "description": ln.get("description"), "quantity": ln["quantity"],
                                         "unit_price_cents": ln["unit_price_cents"],
                                         "amount_cents": ln["quantity"] * ln["unit_price_cents"]})
        return self.get_bill(bill_id)

    def create_item_receipt(self, receipt: dict) -> dict:
        row = {"id": receipt.get("id") or f"RCV-{uuid.uuid4().hex[:4].upper()}", **receipt}
        with tx() as c:
            insert(c, "item_receipts", row)
        return row

    def add_po_line(self, po_id: str, line: dict) -> dict:
        n = len(query("SELECT id FROM po_lines WHERE po_id = ?", (po_id,))) + 1
        row = {"id": f"{po_id}-L{n}", "po_id": po_id, "line_no": n, **line}
        with tx() as c:
            insert(c, "po_lines", row)
        return row


def dumps(obj) -> str:
    return json.dumps(obj, default=str)
