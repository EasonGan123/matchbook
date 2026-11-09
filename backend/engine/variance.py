"""Deterministic variance engine.

Compares every bill line against its PO line, the received quantity and the contract
price effective on the invoice date. Output is line-level findings in integer cents.
No model is involved here: the agent reads documents, this module does the math.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from engine.money import pct, qty, usd

# Finding codes. INFO findings explain a variance but are not disputes.
DISPUTE_CODES = {
    "PRICE_ABOVE_CONTRACT", "PO_ABOVE_CONTRACT", "PRICE_ABOVE_PO", "QTY_OVER_RECEIPT",
    "NO_RECEIPT", "LINE_NOT_ON_PO", "DUPLICATE_OF_PAID", "CONTRACT_CONFLICT",
}
INFO_CODES = {"PRICE_MATCHES_CONTRACT"}


@dataclass
class Tolerance:
    # Ramp's three-way match tolerance on unit price vs PO, used only when no contract applies.
    po_price_pct: float = 2.0
    # Contract prices are exact.
    contract_price_cents: int = 0
    qty_units: int = 0


@dataclass
class Finding:
    code: str
    detail: str
    amount_cents: int
    formula: str
    evidence: list[str]
    bill_line_id: str | None = None
    sku: str | None = None
    quantity: int | None = None
    billed_unit_cents: int | None = None
    expected_unit_cents: int | None = None
    severity: str = "dispute"


@dataclass
class LineView:
    bill_line_id: str
    sku: str
    description: str
    quantity: int
    billed_unit_cents: int
    po_unit_cents: int | None
    po_qty: int | None
    contract_unit_cents: int | None
    contract_ref: dict | None
    received_qty: int | None


@dataclass
class VarianceReport:
    bill_id: str
    invoice_date: str
    findings: list[Finding] = field(default_factory=list)
    lines: list[LineView] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)

    @property
    def disputes(self) -> list[Finding]:
        return [f for f in self.findings if f.code in DISPUTE_CODES]

    @property
    def total_cents(self) -> int:
        return sum(f.amount_cents for f in self.disputes)

    @property
    def clean(self) -> bool:
        return not self.disputes

    def to_dict(self) -> dict:
        d = asdict(self)
        d["total_cents"] = self.total_cents
        d["clean"] = self.clean
        return d


def contract_prices_on(contracts: list[dict], sku: str, on: str) -> list[dict]:
    """Every price-schedule entry for `sku` effective on date `on` (ISO dates compare as strings)."""
    hits = []
    for k in contracts:
        terms = k.get("terms") or {}
        if not (k["effective_start"] <= on <= k["effective_end"]):
            continue
        for entry in terms.get("price_schedule", []):
            if entry["sku"] == sku and entry["effective_from"] <= on <= entry["effective_to"]:
                hits.append({**entry, "contract_id": k["id"], "contract_title": k.get("title")})
    return hits


def _cref(entry: dict) -> str:
    return f"contract:{entry['contract_id']}#{entry['ref']['section']}"


def compute_variances(bill: dict, po: dict | None, receipts: list[dict], contracts: list[dict],
                      vendor_bills: list[dict], tol: Tolerance | None = None) -> VarianceReport:
    tol = tol or Tolerance()
    rep = VarianceReport(bill_id=bill["id"], invoice_date=bill["invoice_date"])
    on = bill["invoice_date"]
    po_lines = {pl["id"]: pl for pl in (po or {}).get("lines", [])}
    po_by_sku = {pl["sku"]: pl for pl in po_lines.values()}

    # Duplicate check: same vendor, invoice number and amount as a bill already paid or approved.
    for other in vendor_bills:
        if (other["id"] != bill["id"] and other["invoice_number"] == bill["invoice_number"]
                and other["amount_cents"] == bill["amount_cents"]
                and other["status"] in ("paid", "approved")):
            rep.findings.append(Finding(
                code="DUPLICATE_OF_PAID", amount_cents=bill["amount_cents"],
                detail=f"{bill['invoice_number']} for {usd(bill['amount_cents'])} was already "
                       f"{other['status']}{' on ' + other['paid_on'] if other.get('paid_on') else ''} as bill {other['id']}.",
                formula=f"{usd(bill['amount_cents'])} billed twice",
                evidence=[f"bill:{bill['id']}", f"bill:{other['id']}"]))
    rep.checks.append("duplicate: vendor + invoice number + amount against paid bills")

    for ln in bill["lines"]:
        lid, n = ln["id"], ln["line_no"]
        bref = f"bill:{bill['id']}#L{n}"
        pl = po_lines.get(ln.get("po_line_id")) or po_by_sku.get(ln["sku"])
        prices = contract_prices_on(contracts, ln["sku"], on)
        distinct = {p["unit_price_cents"] for p in prices}
        contract_entry = prices[0] if len(distinct) == 1 else None
        received = None
        if pl:
            rlist = [r for r in receipts if r["po_line_id"] == pl["id"]]
            received = sum(r["quantity"] for r in rlist) if rlist else None
        rep.lines.append(LineView(
            bill_line_id=lid, sku=ln["sku"], description=ln.get("description") or "",
            quantity=ln["quantity"], billed_unit_cents=ln["unit_price_cents"],
            po_unit_cents=pl["unit_price_cents"] if pl else None,
            po_qty=pl["quantity"] if pl else None,
            contract_unit_cents=contract_entry["unit_price_cents"] if contract_entry else None,
            contract_ref=({"contract_id": contract_entry["contract_id"], **contract_entry["ref"]}
                          if contract_entry else None),
            received_qty=received))

        if not pl:
            rep.findings.append(Finding(
                code="LINE_NOT_ON_PO", bill_line_id=lid, sku=ln["sku"], quantity=ln["quantity"],
                billed_unit_cents=ln["unit_price_cents"], amount_cents=ln["amount_cents"],
                detail=f"Line {n} \"{ln.get('description')}\" has no matching line on {bill.get('po_id')}.",
                formula=f"{qty(ln['quantity'])} × {usd(ln['unit_price_cents'])} = {usd(ln['amount_cents'])} not on PO",
                evidence=[bref, f"po:{bill.get('po_id')}"]))
            continue

        billed, po_price, q = ln["unit_price_cents"], pl["unit_price_cents"], ln["quantity"]
        pref = f"po:{pl['po_id']}#L{pl['line_no']}"

        # Price
        if len(distinct) > 1:
            entries = sorted(prices, key=lambda p: p["contract_id"])
            rep.findings.append(Finding(
                code="CONTRACT_CONFLICT", bill_line_id=lid, sku=ln["sku"], quantity=q,
                billed_unit_cents=billed, expected_unit_cents=None,
                amount_cents=max(0, (billed - po_price) * q),
                detail=f"{len(entries)} contracts set different prices for {ln['sku']} on {on}: "
                       + ", ".join(f"{e['contract_id']} {usd(e['unit_price_cents'])}" for e in entries)
                       + f". Measured against the PO ({usd(po_price)}) until a person decides which contract governs.",
                formula=f"{qty(q)} × ({usd(billed)} − {usd(po_price)}) = {usd(max(0, (billed - po_price) * q))}",
                evidence=[bref, pref, *[_cref(e) for e in entries]]))
        elif contract_entry:
            cp = contract_entry["unit_price_cents"]
            cref = _cref(contract_entry)
            if billed > po_price and billed <= cp:
                rep.findings.append(Finding(
                    code="PRICE_MATCHES_CONTRACT", severity="info", bill_line_id=lid, sku=ln["sku"],
                    quantity=q, billed_unit_cents=billed, expected_unit_cents=cp,
                    amount_cents=(billed - po_price) * q,
                    detail=f"Billed {usd(billed)} is above PO {usd(po_price)} but equals the contract price "
                           f"in effect on {on} ({contract_entry['contract_id']} §{contract_entry['ref']['section']}).",
                    formula=f"{qty(q)} × ({usd(billed)} − {usd(po_price)}) = {usd((billed - po_price) * q)} above PO, within contract",
                    evidence=[bref, pref, cref]))
            elif billed > cp + tol.contract_price_cents:
                # Bill agrees with PO but both exceed the contract: invisible to three-way match.
                code = "PO_ABOVE_CONTRACT" if billed == po_price else "PRICE_ABOVE_CONTRACT"
                amt = (billed - cp) * q
                rep.findings.append(Finding(
                    code=code, bill_line_id=lid, sku=ln["sku"], quantity=q, billed_unit_cents=billed,
                    expected_unit_cents=cp, amount_cents=amt,
                    detail=(f"Billed {usd(billed)} vs contract {usd(cp)} in effect on {on}"
                            + (f"; the PO also carries the stale {usd(po_price)}." if code == "PO_ABOVE_CONTRACT"
                               else f" (PO {usd(po_price)}).")),
                    formula=f"{qty(q)} × ({usd(billed)} − {usd(cp)}) = {usd(amt)}",
                    evidence=[bref, pref, cref]))
        elif billed > po_price and pct(billed - po_price, po_price) > tol.po_price_pct:
            amt = (billed - po_price) * q
            rep.findings.append(Finding(
                code="PRICE_ABOVE_PO", bill_line_id=lid, sku=ln["sku"], quantity=q, billed_unit_cents=billed,
                expected_unit_cents=po_price, amount_cents=amt,
                detail=f"Billed {usd(billed)} is {pct(billed - po_price, po_price)}% above PO {usd(po_price)}; no contract price found.",
                formula=f"{qty(q)} × ({usd(billed)} − {usd(po_price)}) = {usd(amt)}",
                evidence=[bref, pref]))

        # Quantity
        if received is None:
            rep.findings.append(Finding(
                code="NO_RECEIPT", bill_line_id=lid, sku=ln["sku"], quantity=q, billed_unit_cents=billed,
                amount_cents=ln["amount_cents"],
                detail=f"No item receipt is recorded against {pl['po_id']} line {pl['line_no']}.",
                formula=f"{qty(q)} × {usd(billed)} = {usd(ln['amount_cents'])} billed, 0 received",
                evidence=[bref, pref]))
        elif q > received + tol.qty_units:
            over = q - received
            rref = [f"receipt:{r['id']}" for r in receipts if r["po_line_id"] == pl["id"]]
            rep.findings.append(Finding(
                code="QTY_OVER_RECEIPT", bill_line_id=lid, sku=ln["sku"], quantity=over,
                billed_unit_cents=billed, amount_cents=over * billed,
                detail=f"Billed {qty(q)} units, received {qty(received)}.",
                formula=f"({qty(q)} − {qty(received)}) × {usd(billed)} = {usd(over * billed)}",
                evidence=[bref, pref, *rref]))

    rep.checks += [
        f"price: bill vs PO (tolerance {tol.po_price_pct}%) and vs contract price effective {on} (exact)",
        f"quantity: billed vs received (tolerance {tol.qty_units} units)",
        "coverage: every bill line maps to a PO line",
    ]
    return rep
