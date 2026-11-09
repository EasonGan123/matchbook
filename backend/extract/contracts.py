"""Contract PDF → structured terms, via Claude vision. Run once, cached as JSON.

    cd backend && uv run python -m extract.contracts       (needs Anthropic credentials)

Writes fixtures/extracted/<contract_id>.json; `make reset` then loads those terms.
Until this has been run, the seed falls back to the fixture's ground truth and marks
it "_source": "fixture-ground-truth", which the UI shows.
"""
from __future__ import annotations

import base64
import json

from agent.llm import MODEL
from db.conn import ROOT
from db.seed import load_seed

OUT = ROOT / "fixtures" / "extracted"

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "title", "effective_start", "effective_end", "payment_terms", "price_schedule", "clauses"],
    "properties": {
        "id": {"type": "string"}, "title": {"type": "string"},
        "effective_start": {"type": "string", "description": "YYYY-MM-DD"},
        "effective_end": {"type": "string", "description": "YYYY-MM-DD"},
        "payment_terms": {"type": "string"},
        "price_schedule": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["sku", "description", "unit_price_cents", "unit", "effective_from", "effective_to", "ref"],
            "properties": {
                "sku": {"type": "string"}, "description": {"type": "string"},
                "unit_price_cents": {"type": "integer"}, "unit": {"type": "string"},
                "effective_from": {"type": "string"}, "effective_to": {"type": "string"},
                "ref": {"type": "object", "additionalProperties": False, "required": ["page", "section", "quote"],
                        "properties": {"page": {"type": "integer"}, "section": {"type": "string"},
                                       "quote": {"type": "string"}}}}}},
        "clauses": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["section", "page", "heading", "text"],
            "properties": {"section": {"type": "string"}, "page": {"type": "integer"},
                           "heading": {"type": "string"}, "text": {"type": "string"}}}},
    },
}

PROMPT = """Extract this supply contract's commercial terms as JSON.
- price_schedule: one entry per SKU price and date range. Escalation clauses that set a new price on a date become their own entry. Convert prices to integer cents. ref.quote is the exact sentence, ref.page the PDF page.
- clauses: pricing, term, invoicing, billing and escalation clauses only, quoted verbatim with section and page.
- Dates as YYYY-MM-DD. Use the contract id printed in the page header."""


def extract(contract_id: str) -> dict:
    import anthropic
    client = anthropic.Anthropic()
    pdf = (ROOT / "fixtures" / "pdf" / f"{contract_id}.pdf").read_bytes()
    resp = client.messages.create(
        model=MODEL, max_tokens=16000,
        thinking={"type": "adaptive"}, output_config={"effort": "medium",
                                                      "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                            "data": base64.standard_b64encode(pdf).decode()}},
            {"type": "text", "text": PROMPT}]}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"{contract_id}: model declined")
    text = next(b.text for b in resp.content if b.type == "text")
    terms = json.loads(text)
    terms["vendor_id"] = next(k["vendor_id"] for k in load_seed()["contracts"] if k["id"] == contract_id)
    terms["_source"] = "claude-vision"
    terms["_model"] = MODEL
    return terms


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for k in load_seed()["contracts"]:
        terms = extract(k["id"])
        (OUT / f"{k['id']}.json").write_text(json.dumps(terms, indent=1))
        truth = {(p["sku"], p["unit_price_cents"], p["effective_from"]) for p in k["price_schedule"]}
        got = {(p["sku"], p["unit_price_cents"], p["effective_from"]) for p in terms["price_schedule"]}
        print(f"{k['id']}: {'OK' if truth == got else 'MISMATCH ' + str(got ^ truth)}")


if __name__ == "__main__":
    main()
