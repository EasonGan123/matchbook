"""Case orchestration: ingest → gather → diagnose → draft → approve → follow up → sync.

Each blocked bill becomes one case. The agent reasons inside a stage; transitions,
writes to Ramp and anything with money attached happen here, in code.
"""
from __future__ import annotations

import json
import threading
import time
import uuid

from agent import prompts
from agent.llm import LLMError, get_llm, mode
from agent.loop import Usage, pace, run_agent
from agent.tools import READ_TOOLS, ROOT_CAUSES, SUBMIT_DIAGNOSIS, SUBMIT_DRAFT, SUBMIT_REPLY, ToolBox, scan_injection
from db.conn import insert, loads, now_iso, query, query_one, tx, update
from db.seed import load_scenarios
from engine.money import usd
from engine.validator import render, validate
from engine.variance import compute_variances
from orchestrator import playbooks as pb
from orchestrator.state import TERMINAL, check
from ramp_client import get_ramp_client

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock(case_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(case_id, threading.Lock())


# ---------------------------------------------------------------- events / state

def emit(case_id: str, kind: str, title: str, data: dict | None = None) -> None:
    with tx() as c:
        insert(c, "case_events", {"case_id": case_id, "ts": now_iso(), "kind": kind, "title": title,
                                  "data_json": json.dumps(data or {}, default=str)})


def get_case(case_id: str) -> dict | None:
    return query_one("SELECT * FROM cases WHERE id = ?", (case_id,))


def set_case(case_id: str, **fields) -> None:
    with tx() as c:
        update(c, "cases", case_id, {**fields, "updated_at": now_iso()})


def transition(case_id: str, to: str, reason: str = "") -> None:
    case = get_case(case_id)
    check(case["state"], to)
    set_case(case_id, state=to)
    emit(case_id, "state", f"{case['state']} → {to}", {"from": case["state"], "to": to, "reason": reason})


def escalate(case_id: str, reason: str) -> None:
    if get_case(case_id)["state"] not in TERMINAL:
        transition(case_id, "ESCALATED", reason)
    set_case(case_id, run_status="idle", playbook="escalate")
    emit(case_id, "escalation", "Escalated to a person", {"reason": reason})


def _scenario_for(bill_id: str) -> dict | None:
    return next((s for s in load_scenarios() if s["bill_id"] == bill_id), None)


def case_id_for(bill_id: str) -> str:
    return "MB-" + bill_id.removeprefix("B-")


# ---------------------------------------------------------------- 1. ingest

def ingest() -> list[str]:
    """Open one case per exception bill (idempotent on bill id), plus a contract sweep that
    catches bills where invoice and PO agree but both exceed the contract."""
    ramp = get_ramp_client()
    opened = []
    candidates = [(b, "ramp_flag") for b in ramp.list_bills("exception")]
    for b in ramp.list_bills("pending_approval"):
        po = ramp.get_purchase_order(b["po_id"]) if b.get("po_id") else None
        rep = compute_variances(b, po, ramp.list_item_receipts(b["po_id"]) if po else [],
                                ramp.list_contracts(b["vendor_id"]), ramp.list_vendor_bills(b["vendor_id"]))
        if any(f.code == "PO_ABOVE_CONTRACT" for f in rep.findings):
            candidates.append((b, "contract_sweep"))
    for b, source in candidates:
        cid = case_id_for(b["id"])
        if query_one("SELECT id FROM cases WHERE bill_id = ?", (b["id"],)):
            continue
        po = ramp.get_purchase_order(b["po_id"]) if b.get("po_id") else None
        rep = compute_variances(b, po, ramp.list_item_receipts(b["po_id"]) if po else [],
                                ramp.list_contracts(b["vendor_id"]), ramp.list_vendor_bills(b["vendor_id"]))
        sc = _scenario_for(b["id"])
        ts = now_iso()
        with tx() as c:
            insert(c, "cases", {"id": cid, "bill_id": b["id"], "scenario": sc["key"] if sc else None,
                                "source": source, "state": "OPEN", "at_stake_cents": rep.total_cents,
                                "created_at": ts, "updated_at": ts})
        emit(cid, "state", "Case opened", {"to": "OPEN", "source": source,
                                           "reason": b.get("ramp_flag") or "Contract sweep: PO price above contract"})
        opened.append(cid)
    return opened


# ---------------------------------------------------------------- 2-7. run the agent

def start_run(case_id: str) -> bool:
    case = get_case(case_id)
    if not case or case["state"] != "OPEN" or case["run_status"] == "running":
        return False
    set_case(case_id, run_status="running")
    threading.Thread(target=run_case, args=(case_id,), daemon=True).start()
    return True


def run_case(case_id: str) -> None:
    with _lock(case_id):
        try:
            _run_case(case_id)
        except LLMError as e:
            emit(case_id, "error", "Model call failed", {"error": str(e)})
            escalate(case_id, f"Agent could not complete: {e}")
        except Exception as e:  # never leave a case stuck in 'running'
            emit(case_id, "error", "Unexpected error", {"error": repr(e)})
            escalate(case_id, f"Unexpected error: {e!r}")
        finally:
            set_case(case_id, run_status="idle")


def _run_case(case_id: str) -> None:
    case = get_case(case_id)
    if case["state"] != "OPEN":
        return
    ramp = get_ramp_client()
    llm = get_llm(case["scenario"] or case["bill_id"])
    started = time.time()
    set_case(case_id, started_at=now_iso())
    emit(case_id, "run", "Matchbook picked up the case", {"mode": llm.kind if hasattr(llm, "kind") else mode()})

    ev = lambda kind, title, data=None: emit(case_id, kind, title, data)
    gathered = {"done": False}

    def on_gathered():
        if not gathered["done"]:
            gathered["done"] = True
            transition(case_id, "CONTEXT_GATHERED", "Bill, PO, receipts and contracts retrieved")

    box = ToolBox(ramp, ev, on_gathered)
    bill = ramp.get_bill(case["bill_id"])
    usage = Usage()

    # Stage 2-4: gather context, compute variances, diagnose
    res = run_agent(llm=llm, stage="diagnose", system=prompts.DIAGNOSE, tools=[*READ_TOOLS, SUBMIT_DIAGNOSIS],
                    terminal="submit_diagnosis", toolbox=box, emit=ev,
                    user=(f"Bill {bill['id']} ({bill['invoice_number']} from {bill['vendor']['name']}) needs review. "
                          f"Ramp's flag: {bill.get('ramp_flag') or 'none (opened by the contract sweep)'}. "
                          "Investigate and submit your diagnosis."))
    usage.input_tokens += res.usage.input_tokens
    usage.output_tokens += res.usage.output_tokens
    dx = res.output
    if not gathered["done"]:
        on_gathered()
    report = box.report
    if report is None:  # the agent skipped the engine; code runs it anyway
        box.call("compute_variances", {"bill_id": bill["id"]})
        report = box.report

    # Guardrails on the diagnosis
    problems = []
    rc = dx.get("root_cause")
    cited = list(dx.get("evidence_ids") or [])
    if rc not in ROOT_CAUSES:
        problems.append(f"root cause {rc!r} is not in the allowed set")
    if not cited:
        problems.append("no evidence cited")
    unknown_ids = [e for e in cited if e not in box.evidence]
    if unknown_ids:
        problems.append(f"cited evidence the agent never retrieved: {unknown_ids}")
    if rc in pb.SUPPORT and not pb.supporting(report, rc):
        problems.append(f"{rc} is not supported by any variance engine finding")
    conflict = [f for f in report.findings if f.code == "CONTRACT_CONFLICT"]
    injection = bool(box.injections) or bool(dx.get("injection_detected"))

    variance = pb.variance_for(report, rc) if rc in ROOT_CAUSES else report.total_cents
    playbook = pb.PLAYBOOK.get(rc, "escalate")
    set_case(case_id, root_cause=rc, playbook=playbook, variance_cents=variance,
             diagnosis_json=json.dumps({**dx, "problems": problems, "injection_flagged": injection,
                                        "evidence": [box.evidence[e] for e in cited if e in box.evidence]}),
             variance_json=json.dumps(report.to_dict(), default=str),
             tokens_in=usage.input_tokens, tokens_out=usage.output_tokens)
    transition(case_id, "DIAGNOSED", rc or "")
    emit(case_id, "diagnosis", rc or "UNKNOWN", {"summary": dx.get("summary"), "evidence_ids": cited,
                                                  "variance_cents": variance, "problems": problems})
    if injection:
        emit(case_id, "security", "Prompt injection ignored", {
            "detail": "Vendor content attempted to instruct the agent. No tool can approve or pay; "
                      "the case continues on the merits.", "matches": box.injections})

    if problems:
        return escalate(case_id, "; ".join(problems))
    if conflict:
        return escalate(case_id, conflict[0].detail)
    if rc == "UNKNOWN":
        return escalate(case_id, dx.get("summary") or "Root cause unknown")

    # Stage 5-6: plan and draft
    po = ramp.get_purchase_order(bill["po_id"]) if bill.get("po_id") else None
    vendor = ramp.get_vendor(bill["vendor_id"])
    contracts = ramp.list_contracts(bill["vendor_id"])
    variables = pb.build_variables(root_cause=rc, bill=bill, po=po, vendor=vendor, report=report,
                                   contracts=contracts, cited=cited, ramp=ramp)
    recipient_type = pb.RECIPIENT[playbook]
    recipient = {"vendor": vendor["contact_email"], "buyer": (po or {}).get("buyer_email"),
                 "controller": "controller@northwind-mfg.example"}[recipient_type]
    emit(case_id, "plan", pb.PLAYBOOK_LABEL[playbook], {"playbook": playbook, "recipient": recipient,
                                                        "variables": variables})

    evidence_text = "\n".join(box.corpus)
    feedback = ""
    draft = check_ = None
    for attempt in range(2):
        user = (f"Playbook: {pb.PLAYBOOK_LABEL[playbook]}. Recipient: {recipient_type} ({recipient}).\n"
                f"Diagnosis: {rc}. {dx.get('summary', '')}\n\n"
                "Variables you may use (write them as {{name}}):\n"
                + "\n".join(f"- {k}: {v}" for k, v in variables.items()) + feedback)
        r = run_agent(llm=llm, stage=f"draft{attempt or ''}", system=prompts.DRAFT, tools=[SUBMIT_DRAFT],
                      terminal="submit_draft", emit=ev, user=user, max_turns=3)
        usage.input_tokens += r.usage.input_tokens
        usage.output_tokens += r.usage.output_tokens
        draft = r.output
        check_ = validate(draft["subject"] + "\n" + draft["body_template"], variables, evidence_text)
        emit(case_id, "validator", check_["summary"], {"ok": check_["ok"], "numbers": check_["numbers"],
                                                       "untraced": check_["untraced"]})
        if check_["ok"]:
            break
        feedback = (f"\n\nYour previous draft was rejected: {check_['summary']}. "
                    "Use variables for every number.")
    set_case(case_id, tokens_in=usage.input_tokens, tokens_out=usage.output_tokens)
    if not check_["ok"]:
        return escalate(case_id, "Draft failed number validation twice")

    subject, _ = render(draft["subject"], variables)
    body, _ = render(draft["body_template"], variables)
    draft_id = f"DR-{uuid.uuid4().hex[:6].upper()}"
    with tx() as c:
        insert(c, "drafts", {"id": draft_id, "case_id": case_id, "recipient_type": recipient_type,
                             "recipient": recipient, "subject": subject, "body_template": draft["body_template"],
                             "body": body, "variables_json": json.dumps(variables),
                             "validation_json": json.dumps(check_), "created_at": now_iso()})
    set_case(case_id, drafted_at=now_iso())
    transition(case_id, "DRAFTED", f"Draft to {recipient_type}")
    emit(case_id, "draft", subject, {"draft_id": draft_id, "recipient": recipient,
                                     "seconds_to_draft": round(time.time() - started, 1)})

    # Stage 7: file the approval request in Ramp
    if pace():
        time.sleep(pace())
    apr = ramp.create_approval_request(bill["id"], {"case_id": case_id, "draft_id": draft_id,
                                                    "approver": "Controller",
                                                    "note": f"{pb.PLAYBOOK_LABEL[playbook]}: {usd(variance)}"})
    transition(case_id, "PENDING_APPROVAL", f"Approval request {apr['id']} filed in Ramp")


# ---------------------------------------------------------------- 7. approval

def approve(case_id: str, approver: str = "Controller", note: str = "") -> dict:
    with _lock(case_id):
        case = get_case(case_id)
        if case["state"] != "PENDING_APPROVAL":
            raise ValueError(f"case is {case['state']}, not awaiting approval")
        ramp = get_ramp_client()
        apr = query_one("SELECT * FROM approvals WHERE case_id = ? AND status = 'pending' "
                        "ORDER BY requested_at DESC", (case_id,))
        with tx() as c:
            update(c, "approvals", apr["id"], {"status": "approved", "approver": approver,
                                               "decided_at": now_iso(), "note": note or None})
        emit(case_id, "approval", f"Approved by {approver}", {"approval_id": apr["id"], "note": note})
        draft = query_one("SELECT * FROM drafts WHERE case_id = ? ORDER BY created_at DESC", (case_id,))
        playbook = case["playbook"]

        if playbook == "approve_with_note":
            transition(case_id, "RESOLVED", "Bill approved as billed with note")
            _sync(case_id, ramp, case["bill_id"], status="approved", note="Approved with note; PO update requested")
            return get_case(case_id)

        # Outbound: only to the contact on file, never an address from vendor content.
        _send(case_id, draft)
        transition(case_id, "SENT", f"Sent to {draft['recipient']}")
        if playbook == "reject_duplicate":
            transition(case_id, "RESOLVED", "Duplicate rejected")
            _sync(case_id, ramp, case["bill_id"], status="rejected", note="Rejected as duplicate")
            return get_case(case_id)
        transition(case_id, "AWAITING_VENDOR", "Follow-up scheduled every 3 days")
        return get_case(case_id)


def reject(case_id: str, approver: str = "Controller", note: str = "") -> dict:
    with _lock(case_id):
        apr = query_one("SELECT * FROM approvals WHERE case_id = ? AND status = 'pending'", (case_id,))
        if apr:
            with tx() as c:
                update(c, "approvals", apr["id"], {"status": "rejected", "approver": approver,
                                                   "decided_at": now_iso(), "note": note or None})
        emit(case_id, "approval", f"Rejected by {approver}", {"note": note})
        escalate(case_id, f"Controller rejected the draft{': ' + note if note else ''}")
        return get_case(case_id)


def _send(case_id: str, draft: dict) -> None:
    with tx() as c:
        insert(c, "messages", {"id": f"MSG-{uuid.uuid4().hex[:6].upper()}", "case_id": case_id,
                               "direction": "out", "sender": "ap@northwind-mfg.example",
                               "recipient": draft["recipient"], "subject": draft["subject"], "body": draft["body"],
                               "attachment_bill_id": None, "sim_day": get_case(case_id)["sim_day"], "ts": now_iso()})
    emit(case_id, "message", f"Sent to {draft['recipient']}", {"direction": "out", "subject": draft["subject"]})


def _sync(case_id: str, ramp, bill_id: str, *, status: str, note: str) -> None:
    ramp.update_bill(bill_id, {"status": status, "match_status": "clean" if status == "approved" else "rejected"})
    transition(case_id, "SYNCED", note)
    emit(case_id, "sync", f"Bill {bill_id} synced to Ramp as {status}", {"bill_id": bill_id, "status": status})


# ---------------------------------------------------------------- 8. follow-up and close

NUDGE_EVERY_DAYS = 3


def start_fast_forward(case_id: str) -> bool:
    case = get_case(case_id)
    if not case or case["state"] != "AWAITING_VENDOR" or case["run_status"] == "running":
        return False
    set_case(case_id, run_status="running")

    def go():
        try:
            fast_forward(case_id)
        except Exception as e:
            emit(case_id, "error", "Follow-up failed", {"error": repr(e)})
            escalate(case_id, f"Follow-up failed: {e!r}")
        finally:
            set_case(case_id, run_status="idle")

    threading.Thread(target=go, daemon=True).start()
    return True


def fast_forward(case_id: str) -> None:
    """Advance the simulated clock: nudge on the follow-up cadence until the counterparty replies."""
    with _lock(case_id):
        case = get_case(case_id)
        sc = _scenario_for(case["bill_id"]) or {}
        reply = sc.get("reply")
        ramp = get_ramp_client()
        day = case["sim_day"]
        reply_day = reply["after_days"] if reply else None
        while True:
            next_nudge = (day // NUDGE_EVERY_DAYS + 1) * NUDGE_EVERY_DAYS
            if reply_day is not None and reply_day <= next_nudge:
                day = reply_day
                break
            day = next_nudge
            set_case(case_id, sim_day=day)
            draft = query_one("SELECT * FROM drafts WHERE case_id = ? ORDER BY created_at DESC", (case_id,))
            emit(case_id, "nudge", f"Day {day}: no reply, follow-up sent to {draft['recipient']}",
                 {"day": day, "recipient": draft["recipient"]})
            if pace():
                time.sleep(pace())
            if reply_day is None and day >= 9:
                return escalate(case_id, "No reply after three follow-ups")
        set_case(case_id, sim_day=day)
        if pace():
            time.sleep(pace())
        _handle_reply(case_id, ramp, reply, day)


def _handle_reply(case_id: str, ramp, reply: dict, day: int) -> None:
    case = get_case(case_id)
    bill = ramp.get_bill(case["bill_id"])
    vendor = ramp.get_vendor(bill["vendor_id"])
    po = ramp.get_purchase_order(bill["po_id"])
    sender = vendor["contact_email"] if reply["from"] == "vendor" else po["buyer_email"]

    new_bill = None
    if reply.get("corrected_bill"):
        cb = reply["corrected_bill"]
        po_by_sku = {pl["sku"]: pl for pl in po["lines"]}
        new_bill = ramp.create_bill({
            "id": bill["id"] + "-C", "vendor_id": bill["vendor_id"], "po_id": bill["po_id"],
            "invoice_number": cb["invoice_number"], "invoice_date": bill["invoice_date"],
            "due_date": bill["due_date"], "status": "exception", "match_status": "pending",
            "ramp_flag": None, "pdf_path": f"pdf/{bill['id']}-C.pdf", "vendor_notes": None,
            "supersedes": bill["id"], "paid_on": None,
            "lines": [{**ln, "po_line_id": po_by_sku.get(ln["sku"], {}).get("id"),
                       "description": po_by_sku.get(ln["sku"], {}).get("description")} for ln in cb["lines"]]})
    with tx() as c:
        insert(c, "messages", {"id": f"MSG-{uuid.uuid4().hex[:6].upper()}", "case_id": case_id, "direction": "in",
                               "sender": sender, "recipient": "ap@northwind-mfg.example", "subject": reply["subject"],
                               "body": reply["body"], "attachment_bill_id": new_bill["id"] if new_bill else None,
                               "sim_day": day, "ts": now_iso()})
    emit(case_id, "message", f"Day {day}: reply from {sender}",
         {"direction": "in", "subject": reply["subject"], "body": reply["body"],
          "attachment": new_bill["invoice_number"] if new_bill else None})
    hit = scan_injection(reply["body"])
    if hit:
        emit(case_id, "security", "Instruction-like text in reply, treated as data", {"match": hit})

    # Claude reads the reply; code decides what it means for the bill.
    llm = get_llm(case["scenario"] or case["bill_id"])
    r = run_agent(llm=llm, stage="reply", system=prompts.REPLY, tools=[SUBMIT_REPLY],
                  terminal="submit_reply_assessment", emit=lambda k, t, d=None: emit(case_id, k, t, d),
                  user=f"Original issue: {case['root_cause']}.\n\nReply from {sender}:\n<reply>\n{reply['body']}\n</reply>"
                       + (f"\n\nAttachment: corrected invoice {new_bill['invoice_number']}" if new_bill else ""),
                  max_turns=3)
    set_case(case_id, tokens_in=case["tokens_in"] + r.usage.input_tokens,
             tokens_out=case["tokens_out"] + r.usage.output_tokens)
    intent = r.output["intent"]
    emit(case_id, "reply", f"Reply read as: {intent.replace('_', ' ')}", r.output)

    target = bill
    if intent == "corrected_invoice" and new_bill:
        target = new_bill
    elif intent == "receipt_confirmed" and reply.get("receipt"):
        rc = ramp.create_item_receipt({**reply["receipt"], "po_id": po["id"], "received_by": "Confirmed by buyer"})
        emit(case_id, "ramp", f"Item receipt {rc['id']} recorded", rc)
    elif intent == "charge_approved" and reply.get("po_line"):
        pl = ramp.add_po_line(po["id"], reply["po_line"])
        emit(case_id, "ramp", f"PO {po['number']} amended: {pl['description']}", pl)
        # A service line has nothing to receive at the dock; the buyer's confirmation is the receipt.
        rc = ramp.create_item_receipt({"po_id": po["id"], "po_line_id": pl["id"], "quantity": pl["quantity"],
                                       "received_on": bill["invoice_date"], "received_by": "Confirmed by buyer"})
        emit(case_id, "ramp", f"Service receipt {rc['id']} recorded", rc)
    else:
        return escalate(case_id, f"Reply did not resolve the issue ({intent})")

    # Re-match with the same deterministic engine.
    target = ramp.get_bill(target["id"])
    po = ramp.get_purchase_order(target["po_id"])
    rep = compute_variances(target, po, ramp.list_item_receipts(po["id"]), ramp.list_contracts(target["vendor_id"]),
                            ramp.list_vendor_bills(target["vendor_id"]))
    emit(case_id, "engine", f"Re-match on {target['invoice_number']}: " + ("clean" if rep.clean else "still off"),
         rep.to_dict())
    if not rep.clean:
        transition(case_id, "DIAGNOSED", "Correction still does not match")
        return escalate(case_id, "Correction still does not match; handed to AP")
    transition(case_id, "RESOLVED", f"{target['invoice_number']} matches PO, receipt and contract")
    if pace():
        time.sleep(pace())
    if new_bill and target["id"] == new_bill["id"]:
        ramp.update_bill(bill["id"], {"status": "superseded"})
        emit(case_id, "ramp", f"{bill['invoice_number']} marked superseded by {new_bill['invoice_number']}", {})
    _sync(case_id, ramp, target["id"], status="approved", note=f"{target['invoice_number']} approved for payment")


# ---------------------------------------------------------------- reads for the API

def case_detail(case_id: str) -> dict | None:
    case = get_case(case_id)
    if not case:
        return None
    ramp = get_ramp_client()
    bill = ramp.get_bill(case["bill_id"])
    po = ramp.get_purchase_order(bill["po_id"]) if bill.get("po_id") else None
    corrected = query_one("SELECT id FROM bills WHERE supersedes = ?", (bill["id"],))
    return {
        "case": {**case, "diagnosis": loads(case.pop("diagnosis_json")), "variance": loads(case.pop("variance_json")),
                 "playbook_label": pb.PLAYBOOK_LABEL.get(case["playbook"] or "", None)},
        "bill": bill, "po": po,
        "receipts": ramp.list_item_receipts(bill["po_id"]) if po else [],
        "vendor": ramp.get_vendor(bill["vendor_id"]),
        "contracts": ramp.list_contracts(bill["vendor_id"]),
        "corrected_bill": ramp.get_bill(corrected["id"]) if corrected else None,
        "draft": _draft(case_id),
        "approvals": query("SELECT * FROM approvals WHERE case_id = ? ORDER BY requested_at", (case_id,)),
        "messages": query("SELECT * FROM messages WHERE case_id = ? ORDER BY ts", (case_id,)),
        "events": events(case_id),
    }


def _draft(case_id: str) -> dict | None:
    d = query_one("SELECT * FROM drafts WHERE case_id = ? ORDER BY created_at DESC", (case_id,))
    if d:
        d["variables"] = loads(d.pop("variables_json"), {})
        d["validation"] = loads(d.pop("validation_json"), {})
    return d


def events(case_id: str, after: int = 0) -> list[dict]:
    rows = query("SELECT * FROM case_events WHERE case_id = ? AND id > ? ORDER BY id", (case_id, after))
    for r in rows:
        r["data"] = loads(r.pop("data_json"), {})
    return rows


def list_cases() -> list[dict]:
    rows = query("""SELECT c.*, b.invoice_number, b.invoice_date, b.amount_cents, b.ramp_flag, b.status AS bill_status,
                           v.name AS vendor_name
                    FROM cases c JOIN bills b ON b.id = c.bill_id JOIN vendors v ON v.id = b.vendor_id
                    ORDER BY c.at_stake_cents DESC""")
    for r in rows:
        r.pop("diagnosis_json", None)
        r.pop("variance_json", None)
    return rows
