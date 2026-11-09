"""Matchbook's Ramp tools over MCP (stdio).

Exposes the same read tools the agent uses, so any MCP client (Claude Code, Claude
Desktop) can inspect blocked bills the way Matchbook does. Write actions are not
exposed: least privilege. Run:

    cd backend && uv run python -m mcp_server.server
"""
from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer

from agent.tools import ToolBox
from ramp_client import get_ramp_client

server = MCPServer("matchbook-ramp")
_box = ToolBox(get_ramp_client(), emit=lambda *a, **k: None)


def _call(name: str, **args) -> dict:
    out = json.loads(_box.call(name, args))
    _box.flush()
    return out


@server.tool()
def get_bill(bill_id: str) -> dict:
    """Fetch a Ramp Bill Pay bill with line items, match status and Ramp's flag."""
    return _call("get_bill", bill_id=bill_id)


@server.tool()
def get_purchase_order(po_id: str) -> dict:
    """Fetch a purchase order with its lines, buyer and issue date."""
    return _call("get_purchase_order", po_id=po_id)


@server.tool()
def list_item_receipts(po_id: str) -> dict:
    """List goods received against a purchase order."""
    return _call("list_item_receipts", po_id=po_id)


@server.tool()
def search_contracts(vendor_id: str, sku: str = "") -> dict:
    """A vendor's contracts: effective dates, price schedule and clauses with page/section refs."""
    return _call("search_contracts", vendor_id=vendor_id, sku=sku)


@server.tool()
def get_vendor_history(vendor_id: str) -> dict:
    """Vendor contact on file, dispute stats and other bills (for duplicate checks)."""
    return _call("get_vendor_history", vendor_id=vendor_id)


@server.tool()
def compute_variances(bill_id: str) -> dict:
    """Deterministic variance engine: exact line-level variances in cents with evidence ids."""
    return _call("compute_variances", bill_id=bill_id)


if __name__ == "__main__":
    server.run()
