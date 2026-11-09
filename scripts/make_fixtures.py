"""Generate the demo PDFs (contracts, invoices, corrected invoices) from fixtures/seed.json.

    cd backend && uv run python ../scripts/make_fixtures.py

All companies and figures are fictional.
"""
from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "pdf"
INK, MUTED, RED = HexColor("#151412"), HexColor("#6f6a62"), HexColor("#b8372b")
W, H = LETTER
BUYER = "Northwind Manufacturing, 400 Mill Street, Dayton OH"


def usd(c: int) -> str:
    return f"${c // 100:,}.{c % 100:02d}"


def wrap(c: canvas.Canvas, text: str, x: float, y: float, width: float, font="Times-Roman", size=11, lead=15):
    c.setFont(font, size)
    line = ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if c.stringWidth(trial, font, size) > width:
            c.drawString(x, y, line)
            y -= lead
            line = word
        else:
            line = trial
    if line:
        c.drawString(x, y, line)
        y -= lead
    return y


def header(c, left: str, right: str):
    c.setFillColor(INK)
    c.setFont("Courier-Bold", 9)
    c.drawString(54, H - 50, left.upper())
    c.setFont("Courier", 9)
    c.drawRightString(W - 54, H - 50, right.upper())
    c.setStrokeColor(INK)
    c.line(54, H - 58, W - 54, H - 58)


def contract_pdf(k: dict, vendor: dict):
    path = OUT / f"{k['id']}.pdf"
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.setTitle(k["title"])
    pages = max([cl["page"] for cl in k["clauses"]] + [p["ref"]["page"] for p in k["price_schedule"]])
    for page in range(1, pages + 1):
        header(c, vendor["name"], f"{k['id']} · page {page} of {pages}")
        y = H - 100
        if page == 1:
            c.setFont("Times-Bold", 22)
            c.drawString(54, y, k["title"])
            y -= 26
            y = wrap(c, f"Between {vendor['name']} (\"Supplier\") and {BUYER} (\"Buyer\"). "
                        f"Effective {k['effective_start']} through {k['effective_end']}. Payment terms: {k['payment_terms']}.",
                     54, y, W - 108, size=11)
            y -= 10
        for cl in [cl for cl in k["clauses"] if cl["page"] == page]:
            c.setFont("Times-Bold", 12)
            c.drawString(54, y, f"§{cl['section']}  {cl['heading']}")
            y = wrap(c, cl["text"], 54, y - 16, W - 108)
            y -= 12
        if not any(cl["page"] == page for cl in k["clauses"]):
            y = wrap(c, "General terms: warranties, delivery, inspection and acceptance, confidentiality, "
                        "limitation of liability and governing law. Not relevant to pricing.", 54, y, W - 108,
                     font="Times-Italic", size=10)
        c.setFont("Courier", 8)
        c.setFillColor(MUTED)
        c.drawString(54, 40, "FICTIONAL DEMO DOCUMENT · MATCHBOOK")
        c.setFillColor(INK)
        c.showPage()
    c.save()


def invoice_pdf(bill_id: str, vendor: dict, invoice_number: str, invoice_date: str, po_id: str | None,
                lines: list[dict], notes: str | None = None, corrected_of: str | None = None):
    path = OUT / f"{bill_id}.pdf"
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.setTitle(f"{vendor['name']} {invoice_number}")
    header(c, vendor["name"], "Corrected invoice" if corrected_of else "Invoice")
    y = H - 110
    c.setFont("Times-Bold", 26)
    c.drawString(54, y, f"Invoice {invoice_number}")
    c.setFont("Courier", 9)
    y -= 22
    for label, val in [("Date", invoice_date), ("Bill to", BUYER), ("PO", po_id or "-"),
                       ("Remit", vendor["contact_email"])] + ([("Replaces", corrected_of)] if corrected_of else []):
        c.drawString(54, y, f"{label.upper():<10}{val}")
        y -= 13
    y -= 18
    c.line(54, y, W - 54, y)
    y -= 14
    c.setFont("Courier-Bold", 9)
    for x, t in [(54, "SKU"), (140, "DESCRIPTION"), (360, "QTY"), (420, "UNIT"), (W - 54, "AMOUNT")]:
        (c.drawRightString if t == "AMOUNT" else c.drawString)(x, y, t)
    y -= 6
    c.line(54, y, W - 54, y)
    y -= 16
    total = 0
    c.setFont("Times-Roman", 11)
    for ln in lines:
        amt = ln["quantity"] * ln["unit_price_cents"]
        total += amt
        c.drawString(54, y, ln["sku"])
        c.drawString(140, y, (ln.get("description") or "")[:34])
        c.drawString(360, y, f"{ln['quantity']:,}")
        c.drawString(420, y, usd(ln["unit_price_cents"]))
        c.drawRightString(W - 54, y, usd(amt))
        y -= 18
    c.line(54, y, W - 54, y)
    y -= 20
    c.setFont("Times-Bold", 14)
    c.drawRightString(W - 54, y, f"Total due  {usd(total)}")
    if notes:
        y -= 50
        c.setFont("Courier-Bold", 8)
        c.drawString(54, y, "NOTES")
        c.setFillColor(MUTED)
        wrap(c, notes, 54, y - 14, W - 108, font="Times-Italic", size=10)
        c.setFillColor(INK)
    c.setFont("Courier", 8)
    c.setFillColor(MUTED)
    c.drawString(54, 40, "FICTIONAL DEMO DOCUMENT · MATCHBOOK")
    c.save()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    seed = json.loads((ROOT / "fixtures" / "seed.json").read_text())
    scenarios = json.loads((ROOT / "fixtures" / "scenarios.json").read_text())["scenarios"]
    vendors = {v["id"]: v for v in seed["vendors"]}
    for k in seed["contracts"]:
        contract_pdf(k, vendors[k["vendor_id"]])
    for b in seed["bills"]:
        invoice_pdf(b["id"], vendors[b["vendor_id"]], b["invoice_number"], b["invoice_date"], b.get("po_id"),
                    b["lines"], b.get("vendor_notes"))
    bills = {b["id"]: b for b in seed["bills"]}
    for s in scenarios:
        cb = (s.get("reply") or {}).get("corrected_bill")
        if cb:
            b = bills[s["bill_id"]]
            desc = {ln["sku"]: ln["description"] for ln in b["lines"]}
            invoice_pdf(b["id"] + "-C", vendors[b["vendor_id"]], cb["invoice_number"], b["invoice_date"],
                        b.get("po_id"), [{**ln, "description": desc.get(ln["sku"])} for ln in cb["lines"]],
                        corrected_of=b["invoice_number"])
    print(f"Wrote {len(list(OUT.glob('*.pdf')))} PDFs to {OUT}")


if __name__ == "__main__":
    main()
