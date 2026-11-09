"""RampClient: the only way Matchbook touches Ramp.

Going live means swapping MockRampClient for LiveRampClient, not rewriting the agent.
Resource names follow Ramp's Developer API (bills, purchase orders, item receipts,
vendors); field names are simplified here and must be checked against docs.ramp.com.
"""
from __future__ import annotations

import os
from typing import Protocol

from ramp_client.mock import MockRampClient


class RampClient(Protocol):
    # read
    def list_bills(self, status: str | None = None) -> list[dict]: ...
    def get_bill(self, bill_id: str) -> dict | None: ...
    def get_purchase_order(self, po_id: str) -> dict | None: ...
    def list_item_receipts(self, po_id: str) -> list[dict]: ...
    def get_vendor(self, vendor_id: str) -> dict | None: ...
    def list_contracts(self, vendor_id: str) -> list[dict]: ...
    def list_vendor_bills(self, vendor_id: str) -> list[dict]: ...
    # write: called only by the orchestrator, after human approval
    def create_approval_request(self, bill_id: str, payload: dict) -> dict: ...
    def update_bill(self, bill_id: str, patch: dict) -> dict: ...
    def create_bill(self, bill: dict) -> dict: ...
    def create_item_receipt(self, receipt: dict) -> dict: ...
    def add_po_line(self, po_id: str, line: dict) -> dict: ...


class LiveRampClient:
    """Placeholder. Read access exists today via Ramp's Developer API (see ramp-mcp);
    write scopes for approval requests are an open question for Ramp."""

    def __init__(self, token: str):
        self.token = token

    def __getattr__(self, name):
        raise NotImplementedError(f"LiveRampClient.{name} is not implemented in the demo")


def get_ramp_client() -> RampClient:
    if os.environ.get("RAMP_MODE") == "live":
        return LiveRampClient(os.environ["RAMP_API_TOKEN"])
    return MockRampClient()
