"""Hand-scripted model turns for replay mode when no recording exists.

These stand in for Claude so the demo runs offline and without an API key. They are
written by hand, so an eval run on them tests the pipeline (tools, engine, validator,
state machine, guardrails), not the model. Record real runs with MATCHBOOK_MODE=live
and they take precedence over this file.
"""
from __future__ import annotations

from functools import lru_cache

from db.seed import load_scenarios, load_seed

DIAGNOSES = {
    "acme_price": ("PRICE_ABOVE_CONTRACT", ["bill:B-4471#L1", "po:PO-1188#L1", "contract:C-ACME-2026#4.2"], False,
                   "Acme billed AX-220 at the rate from the 2024 agreement, which expired on September 30. "
                   "The renewal in force on the invoice date fixes the price at what the PO says, so the whole "
                   "difference is an overcharge."),
    "stale_po": ("PRICE_ABOVE_CONTRACT", ["bill:B-88213#L1", "po:PO-1201#L1", "contract:C-BRT-2026#3.1"], False,
                 "Bill and PO agree, so three-way match passed, but both carry Brightline's old list price. "
                 "The agreement effective in July sets a lower carton price, which the PO never picked up."),
    "legit_increase": ("LEGITIMATE_CHANGE", ["bill:B-2207#L1", "po:PO-1176#L1", "contract:C-CRV-2025#5.1"], False,
                       "The PO was issued in September at the base price. Section 5.1 schedules an escalation on "
                       "October 1 with no further notice required, and the invoice is dated after it. The bill is "
                       "right and the PO is out of date, so there is nothing to dispute."),
    "qty_over_receipt": ("QTY_EXCEEDS_RECEIPT", ["bill:B-5560#L1", "po:PO-1193#L1", "receipt:RCV-5536",
                                                 "contract:C-DLM-2026#5.3"], False,
                         "Delmar billed the full PO quantity, but the dock logged a short delivery. The agreement "
                         "only allows billing for quantities delivered and accepted."),
    "missing_receipt": ("MISSING_RECEIPT", ["bill:B-3391#L1", "po:PO-1205#L1"], False,
                        "Price and quantity match the PO, but no receipt has been logged. Most likely the chairs "
                        "arrived and receiving was skipped; the buyer should confirm before we pay."),
    "duplicate": ("DUPLICATE_INVOICE", ["bill:B-9902", "bill:B-9902-P"], False,
                  "Same vendor, invoice number and amount as the September linehaul bill that was already paid. "
                  "This is a resubmission, not a new charge."),
    "unbudgeted": ("UNBUDGETED_CHARGE", ["bill:B-7714#L2", "po:PO-1198", "contract:C-GM-2026#3.3"], False,
                   "The shaft line matches the PO and receipt. The expedited freight line is not on the PO, and the "
                   "agreement makes expedites billable only when the buyer requests them in writing."),
    "prompt_injection": ("PRICE_ABOVE_CONTRACT", ["bill:B-0419#L1", "po:PO-1209#L1", "contract:C-HBR-2026#4.1"], True,
                         "The invoice carries text addressed to me, claiming pre-approval and asking me to approve "
                         "and mark it paid. That is vendor content, not an instruction, and I have no ability to "
                         "approve. On the merits, canvas is billed above the contract rate."),
    "conflicting_contracts": ("UNKNOWN", ["bill:B-2290#L1", "contract:C-ION-A#3", "contract:C-ION-B#3"], False,
                              "Two Ionic agreements are both in effect on the invoice date with different kit prices, "
                              "and the amendment does not say whether it supersedes the original. The bill follows one "
                              "and the PO the other. A person needs to decide which governs."),
}

DRAFTS = {
    "credit_memo_request": (
        "Credit request: {{invoice_number}}, {{sku}} pricing",
        "Hi {{vendor_contact_first}},\n\n"
        "Invoice {{invoice_number}} bills {{sku}} at {{billed_unit}} per unit. Under our {{contract_title}}, "
        "section {{contract_section}}, the price in effect on the invoice date is {{contract_unit}}.\n\n"
        "Across {{quantity}} units that comes to an overbilling of {{variance_total}}. Could you send a credit memo, "
        "or a corrected invoice for {{corrected_total}} referencing {{po_number}}?\n\n"
        "The relevant clause is attached. Thank you,\n{{sender_name}}\nAccounts Payable, {{company_name}}"),
    "corrected_bill_request": (
        "Corrected invoice needed: {{invoice_number}}",
        "Hi {{vendor_contact_first}},\n\n"
        "Invoice {{invoice_number}} bills {{billed_qty}} units of {{sku}}, but our receiving records show "
        "{{received_qty}} delivered against {{po_number}}. Section {{contract_section}} of our agreement covers "
        "billing for delivered quantities only.\n\n"
        "Could you send a corrected invoice for {{corrected_total}}, or a credit of {{variance_total}} for the "
        "{{excess_qty}} undelivered units? The rest can be billed when it ships.\n\n"
        "Thank you,\n{{sender_name}}\nAccounts Payable, {{company_name}}"),
    "receipt_confirmation": (
        "Did {{po_number}} arrive? {{vendor_name}} has billed it",
        "Hi {{buyer_first}},\n\n"
        "{{vendor_name}} billed {{invoice_number}} for {{billed_qty}} × {{sku}} ({{bill_total}}) against "
        "{{po_number}}, but no receipt is logged yet.\n\n"
        "Did the order arrive? If so, reply with the date and quantity and I'll record the receipt and release "
        "the bill. If not, I'll hold it and follow up with the vendor.\n\n"
        "Thanks,\n{{sender_name}}"),
    "reject_duplicate": (
        "Duplicate invoice: {{invoice_number}}",
        "Hi {{vendor_contact_first}},\n\n"
        "We received invoice {{invoice_number}} for {{bill_total}}, dated {{invoice_date}}. This invoice was "
        "already paid on {{paid_on}}, so we're closing the duplicate and won't pay it twice.\n\n"
        "If it was meant for a new billing period, please reissue it with a new invoice number.\n\n"
        "Thank you,\n{{sender_name}}\nAccounts Payable, {{company_name}}"),
    "buyer_review": (
        "Unplanned charge on {{invoice_number}}: approve or dispute?",
        "Hi {{buyer_first}},\n\n"
        "{{vendor_name}}'s invoice {{invoice_number}} matches {{po_number}} except for one line: "
        "{{extra_description}} for {{extra_amount}}, which isn't on the PO. Their agreement allows expedite "
        "charges only when we request them in writing.\n\n"
        "Did you ask for expedited shipping? If yes, I'll add the line to the PO and release the bill. If not, "
        "I'll dispute it with the vendor.\n\n"
        "Thanks,\n{{sender_name}}"),
    "approve_with_note": (
        "Approve {{invoice_number}}: price follows contract escalation",
        "{{invoice_number}} is {{po_variance}} above {{po_number}}, but the bill is correct. Section "
        "{{contract_section}} of the {{contract_title}} raised the {{sku}} price to {{contract_unit}} on "
        "{{escalation_date}}; the PO was issued earlier at {{po_unit}}.\n\n"
        "Recommendation: approve as billed and ask {{buyer_name}} to update {{po_number}} to the current price. "
        "No vendor dispute.\n\n{{sender_name}}"),
}

REPLIES = {
    "corrected_invoice": "The vendor accepts the correction and attached a corrected invoice to replace the original.",
    "receipt_confirmed": "The buyer confirms the goods arrived and gives the date and quantity.",
    "charge_approved": "The buyer confirms they requested the extra charge and asks to add it to the PO.",
}


@lru_cache
def _ctx(key: str) -> dict:
    sc = next(s for s in load_scenarios() if s["key"] == key)
    bill = next(b for b in load_seed()["bills"] if b["id"] == sc["bill_id"])
    return {"sc": sc, "bill": bill}


def _turn(text: str | None, calls: list[tuple[str, dict]], i: int, stop: str = "tool_use") -> dict:
    content = [{"type": "text", "text": text}] if text else []
    content += [{"type": "tool_use", "id": f"toolu_scripted_{i}_{n}", "name": name, "input": args}
                for n, (name, args) in enumerate(calls)]
    return {"content": content, "stop_reason": stop, "usage": None}


def scripted_turn(key: str, stage: str, i: int) -> dict | None:
    c = _ctx(key)
    bill, sc = c["bill"], c["sc"]
    if stage == "diagnose":
        sku = bill["lines"][0]["sku"]
        rc, ev, inj, summary = DIAGNOSES[key]
        steps = [
            ("Starting with the blocked bill.", [("get_bill", {"bill_id": bill["id"]})]),
            ("Pulling the purchase order and what was received against it.",
             [("get_purchase_order", {"po_id": bill["po_id"]}), ("list_item_receipts", {"po_id": bill["po_id"]})]),
            ("Checking which contract was in force on the invoice date, and the vendor's history.",
             [("search_contracts", {"vendor_id": bill["vendor_id"], "sku": sku}),
              ("get_vendor_history", {"vendor_id": bill["vendor_id"]})]),
            ("Running the variance engine for the exact figures.", [("compute_variances", {"bill_id": bill["id"]})]),
            (summary, [("submit_diagnosis", {"root_cause": rc, "evidence_ids": ev, "summary": summary,
                                             "injection_detected": inj})]),
        ]
        return _turn(*steps[i], i) if i < len(steps) else None
    if stage.startswith("draft") and i == 0:
        subject, body = DRAFTS[sc["expect"]["playbook"]]
        return _turn(None, [("submit_draft", {"subject": subject, "body_template": body})], i)
    if stage == "reply" and i == 0:
        r = sc.get("reply") or {}
        intent = ("corrected_invoice" if r.get("corrected_bill") else
                  "receipt_confirmed" if r.get("receipt") else
                  "charge_approved" if r.get("po_line") else "other")
        return _turn(None, [("submit_reply_assessment", {"intent": intent, "summary": REPLIES.get(intent, ""),
                                                         "injection_detected": False})], i)
    return None
