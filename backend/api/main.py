"""FastAPI app: mock Ramp Bill Pay (/ramp/...) and Matchbook (/api/...)."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from agent.llm import MODEL, RECORDED, mode
from db.conn import ROOT, db_path
from db.seed import seed
from orchestrator import service
from orchestrator.state import STATES
from ramp_client import get_ramp_client

os.environ.setdefault("MATCHBOOK_PACE", "0.7" if mode() == "replay" else "0")

@asynccontextmanager
async def lifespan(_app):
    if not db_path().exists():
        seed()
    service.ingest()
    yield


app = FastAPI(title="Matchbook", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/fixtures", StaticFiles(directory=ROOT / "fixtures"), name="fixtures")


# ------------------------------------------------------------------ mock Ramp
ramp = get_ramp_client


@app.get("/ramp/bills")
def ramp_bills(status: str | None = None):
    return {"data": ramp().list_bills(status)}


@app.get("/ramp/bills/{bill_id}")
def ramp_bill(bill_id: str):
    return ramp().get_bill(bill_id) or _404("bill")


@app.patch("/ramp/bills/{bill_id}")
def ramp_patch_bill(bill_id: str, patch: dict = Body(...)):
    return ramp().update_bill(bill_id, patch)


@app.post("/ramp/bills/{bill_id}/approval-requests")
def ramp_approval(bill_id: str, payload: dict = Body(...)):
    return ramp().create_approval_request(bill_id, payload)


@app.get("/ramp/purchase-orders/{po_id}")
def ramp_po(po_id: str):
    return ramp().get_purchase_order(po_id) or _404("purchase order")


@app.get("/ramp/item-receipts")
def ramp_receipts(po_id: str):
    return {"data": ramp().list_item_receipts(po_id)}


@app.get("/ramp/vendors/{vendor_id}")
def ramp_vendor(vendor_id: str):
    return ramp().get_vendor(vendor_id) or _404("vendor")


@app.get("/ramp/contracts")
def ramp_contracts(vendor_id: str):
    return {"data": ramp().list_contracts(vendor_id)}


@app.post("/ramp/sim/vendor-reply")
def sim_vendor_reply(payload: dict = Body(...)):
    """Trigger the simulated counterparty for a case (same as the UI's fast-forward)."""
    if not service.start_fast_forward(payload["case_id"]):
        raise HTTPException(409, "case is not awaiting a reply")
    return {"ok": True}


# ------------------------------------------------------------------ Matchbook
@app.get("/api/meta")
def meta():
    m = mode()
    replay = "recorded" if RECORDED.exists() and any(RECORDED.iterdir()) else "scripted"
    return {"mode": m if m == "live" else f"replay-{replay}", "model": MODEL, "states": STATES,
            "company": "Northwind Manufacturing"}


@app.get("/api/cases")
def cases():
    return {"data": service.list_cases()}


@app.get("/api/cases/{case_id}")
def case(case_id: str):
    return service.case_detail(case_id) or _404("case")


@app.post("/api/cases/{case_id}/run")
def run(case_id: str):
    if not service.start_run(case_id):
        raise HTTPException(409, "case already ran or is running")
    return {"ok": True}


@app.post("/api/cases/{case_id}/approve")
def approve(case_id: str, body: dict = Body(default={})):
    try:
        return service.approve(case_id, body.get("approver", "Controller"), body.get("note", ""))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/cases/{case_id}/reject")
def reject(case_id: str, body: dict = Body(default={})):
    return service.reject(case_id, body.get("approver", "Controller"), body.get("note", ""))


@app.post("/api/cases/{case_id}/fast-forward")
def fast_forward(case_id: str):
    if not service.start_fast_forward(case_id):
        raise HTTPException(409, "case is not awaiting a reply")
    return {"ok": True}


@app.get("/api/cases/{case_id}/stream")
async def stream(case_id: str, after: int = 0):
    """Server-sent events: the case's audit log as it grows."""
    if not service.get_case(case_id):
        _404("case")

    async def gen():
        last = after
        idle = 0
        while idle < 1200:  # ~5 minutes without news, then close; the client reconnects
            evs = service.events(case_id, last)
            for e in evs:
                last = e["id"]
                yield f"id: {e['id']}\nevent: case_event\ndata: {json.dumps(e, default=str)}\n\n"
            idle = 0 if evs else idle + 1
            if not evs and idle % 60 == 0:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/admin/reset")
def reset():
    seed()
    service.ingest()
    return {"ok": True}


@app.get("/api/evals")
def evals():
    p = ROOT / "evals" / "results" / "latest.json"
    if not p.exists():
        return {"data": None}
    return {"data": json.loads(p.read_text())}


@app.post("/api/evals/run")
def evals_run():
    env = {**os.environ, "MATCHBOOK_DB": str(ROOT / "evals" / "results" / "eval.db"), "MATCHBOOK_PACE": "0"}
    proc = subprocess.run([sys.executable, str(ROOT / "evals" / "run_evals.py")], cwd=ROOT / "backend",
                          env=env, capture_output=True, text=True, timeout=900)
    return {"ok": proc.returncode == 0, "output": proc.stdout[-4000:], "data": evals()["data"]}


def _404(what: str):
    raise HTTPException(404, f"{what} not found")
