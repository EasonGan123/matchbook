"""Root cause → playbook, and the variables code fills into drafts."""
from __future__ import annotations

from engine.money import qty, usd
from engine.variance import VarianceReport

COMPANY = "Northwind Manufacturing"
SENDER = "Jamie Chen"

PLAYBOOK = {
    "PRICE_ABOVE_CONTRACT": "credit_memo_request",
    "QTY_EXCEEDS_RECEIPT": "corrected_bill_request",
    "MISSING_RECEIPT": "receipt_confirmation",
    "DUPLICATE_INVOICE": "reject_duplicate",
    "UNBUDGETED_CHARGE": "buyer_review",
    "LEGITIMATE_CHANGE": "approve_with_note",
    "UNKNOWN": "escalate",
}

PLAYBOOK_LABEL = {
    "credit_memo_request": "Credit memo request to vendor",
    "corrected_bill_request": "Corrected invoice request to vendor",
    "receipt_confirmation": "Receipt confirmation from buyer",
    "reject_duplicate": "Reject duplicate, notify vendor",
    "buyer_review": "Buyer approves or disputes the charge",
    "approve_with_note": "Approve with note, no dispute",
    "escalate": "Escalate to a person",
}

RECIPIENT = {
    "credit_memo_request": "vendor", "corrected_bill_request": "vendor", "reject_duplicate": "vendor",
    "receipt_confirmation": "buyer", "buyer_review": "buyer", "approve_with_note": "controller",
}

# Which engine findings can support each root cause. A diagnosis with no supporting
# finding is inconsistent with the math and gets escalated.
SUPPORT = {
    "PRICE_ABOVE_CONTRACT": {"PRICE_ABOVE_CONTRACT", "PO_ABOVE_CONTRACT"},
    "QTY_EXCEEDS_RECEIPT": {"QTY_OVER_RECEIPT"},
    "MISSING_RECEIPT": {"NO_RECEIPT"},
    "DUPLICATE_INVOICE": {"DUPLICATE_OF_PAID"},
    "UNBUDGETED_CHARGE": {"LINE_NOT_ON_PO"},
    "LEGITIMATE_CHANGE": {"PRICE_MATCHES_CONTRACT"},
}


def supporting(report: VarianceReport, root_cause: str):
    codes = SUPPORT.get(root_cause)
    if codes is None:
        return list(report.findings)
    return [f for f in report.findings if f.code in codes]


def variance_for(report: VarianceReport, root_cause: str) -> int:
    if root_cause == "LEGITIMATE_CHANGE":
        return 0
    if root_cause == "UNKNOWN":
        return report.total_cents
    return sum(f.amount_cents for f in supporting(report, root_cause))


def build_variables(*, root_cause: str, bill: dict, po: dict | None, vendor: dict, report: VarianceReport,
                    contracts: list[dict], cited: list[str], ramp) -> dict[str, str]:
    first = lambda s: (s or "").split()[0] if s else "there"
    v: dict[str, str] = {
        "invoice_number": bill["invoice_number"], "invoice_date": bill["invoice_date"],
        "bill_total": usd(bill["amount_cents"]), "vendor_name": vendor["name"],
        "vendor_contact_first": first(vendor.get("contact_name")),
        "po_number": (po or {}).get("number", ""), "buyer_name": (po or {}).get("buyer_name", ""),
        "buyer_first": first((po or {}).get("buyer_name")), "sender_name": SENDER, "company_name": COMPANY,
    }
    fs = supporting(report, root_cause)
    f = fs[0] if fs else None
    total = variance_for(report, root_cause)
    v["variance_total"] = usd(total)
    v["corrected_total"] = usd(bill["amount_cents"] - total)

    # Contract the agent cited (first one), for section and title.
    cref = next((c for c in cited if c.startswith("contract:")), None)
    if cref:
        cid, _, sec = cref.removeprefix("contract:").partition("#")
        k = next((k for k in contracts if k["id"] == cid), None)
        if k:
            v["contract_title"] = k["title"]
            v["contract_section"] = sec
            entry = next((p for p in k["terms"].get("price_schedule", []) if p["ref"]["section"] == sec), None)
            if entry:
                v["escalation_date"] = entry["effective_from"]

    if f is not None:
        line = next((ln for ln in bill["lines"] if ln["id"] == f.bill_line_id), bill["lines"][0])
        v.update({"sku": line["sku"], "quantity": qty(line["quantity"]), "billed_qty": qty(line["quantity"]),
                  "billed_unit": usd(line["unit_price_cents"])})
        lv = next((x for x in report.lines if x.bill_line_id == line["id"]), None)
        if lv:
            if lv.po_unit_cents is not None:
                v["po_unit"] = usd(lv.po_unit_cents)
            if lv.contract_unit_cents is not None:
                v["contract_unit"] = usd(lv.contract_unit_cents)
            if lv.received_qty is not None:
                v["received_qty"] = qty(lv.received_qty)
        if f.code == "QTY_OVER_RECEIPT":
            v["excess_qty"] = qty(f.quantity)
        if f.code == "PRICE_MATCHES_CONTRACT":
            v["po_variance"] = usd(f.amount_cents)
        if f.code == "LINE_NOT_ON_PO":
            v["extra_description"] = line.get("description") or line["sku"]
            v["extra_amount"] = usd(f.amount_cents)
        if f.code == "DUPLICATE_OF_PAID":
            other_id = next((e.removeprefix("bill:") for e in f.evidence if e != f"bill:{bill['id']}"), None)
            other = ramp.get_bill(other_id) if other_id else None
            if other and other.get("paid_on"):
                v["paid_on"] = other["paid_on"]
    elif bill["lines"]:
        v["sku"] = bill["lines"][0]["sku"]
    return v
