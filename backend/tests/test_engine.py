"""Unit tests for the deterministic core. Run: make test"""
import pytest

from db.seed import seed
from engine.validator import validate
from engine.variance import compute_variances
from ramp_client.mock import MockRampClient


@pytest.fixture(scope="module")
def ramp(tmp_path_factory):
    seed()
    return MockRampClient()


def report(ramp, bill_id):
    b = ramp.get_bill(bill_id)
    po = ramp.get_purchase_order(b["po_id"])
    return compute_variances(b, po, ramp.list_item_receipts(b["po_id"]),
                             ramp.list_contracts(b["vendor_id"]), ramp.list_vendor_bills(b["vendor_id"]))


def codes(rep):
    return sorted(f.code for f in rep.findings)


def test_acme_price_above_contract(ramp):
    rep = report(ramp, "B-4471")
    assert codes(rep) == ["PRICE_ABOVE_CONTRACT"]
    f = rep.findings[0]
    assert f.amount_cents == 160_000  # 4,000 × $0.40
    assert f.expected_unit_cents == 420
    assert "contract:C-ACME-2026#4.2" in f.evidence  # renewal, not the expired 2024 contract
    assert f.formula == "4,000 × ($4.60 − $4.20) = $1,600.00"


def test_stale_po_invisible_to_three_way_match(ramp):
    rep = report(ramp, "B-88213")
    assert codes(rep) == ["PO_ABOVE_CONTRACT"]
    assert rep.total_cents == 62_500


def test_escalation_clause_is_not_a_dispute(ramp):
    rep = report(ramp, "B-2207")
    assert codes(rep) == ["PRICE_MATCHES_CONTRACT"]
    assert rep.clean and rep.total_cents == 0


def test_qty_over_receipt(ramp):
    rep = report(ramp, "B-5560")
    assert codes(rep) == ["QTY_OVER_RECEIPT"]
    assert rep.total_cents == 60_000


def test_missing_receipt(ramp):
    rep = report(ramp, "B-3391")
    assert codes(rep) == ["NO_RECEIPT"]
    assert rep.total_cents == 740_000


def test_duplicate(ramp):
    rep = report(ramp, "B-9902")
    assert codes(rep) == ["DUPLICATE_OF_PAID"]
    assert "bill:B-9902-P" in rep.findings[0].evidence


def test_unbudgeted_line(ramp):
    rep = report(ramp, "B-7714")
    assert codes(rep) == ["LINE_NOT_ON_PO"]
    assert rep.total_cents == 48_000


def test_conflicting_contracts(ramp):
    rep = report(ramp, "B-2290")
    assert codes(rep) == ["CONTRACT_CONFLICT"]
    assert {"contract:C-ION-A#3", "contract:C-ION-B#3"} <= set(rep.findings[0].evidence)


def test_validator_accepts_templated_amounts():
    v = validate("Please credit {{variance_total}} on {{invoice_number}}.",
                 {"variance_total": "$1,600.00", "invoice_number": "INV-4471"}, "INV-4471")
    assert v["ok"], v


def test_validator_rejects_literal_amount():
    v = validate("Please credit $1,600.00 on {{invoice_number}}.",
                 {"variance_total": "$1,600.00", "invoice_number": "INV-4471"}, "INV-4471 $1,600.00")
    assert not v["ok"]


def test_validator_rejects_invented_number():
    v = validate("Credit {{variance_total}} within 7 days.", {"variance_total": "$1,600.00"}, "Net 30 15 days")
    assert not v["ok"] and v["untraced"] == ["7"]
