-- Mock Ramp records (shaped after Ramp's Developer API; verify field names against docs.ramp.com)
CREATE TABLE vendors (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, contact_name TEXT, contact_email TEXT,
  payment_terms TEXT, stats_json TEXT
);
CREATE TABLE purchase_orders (
  id TEXT PRIMARY KEY, vendor_id TEXT NOT NULL, number TEXT, issued_on TEXT,
  buyer_name TEXT, buyer_email TEXT, department TEXT, memo TEXT
);
CREATE TABLE po_lines (
  id TEXT PRIMARY KEY, po_id TEXT NOT NULL, line_no INTEGER, sku TEXT, description TEXT,
  quantity INTEGER, unit_price_cents INTEGER
);
CREATE TABLE item_receipts (
  id TEXT PRIMARY KEY, po_id TEXT NOT NULL, po_line_id TEXT NOT NULL, received_on TEXT,
  quantity INTEGER, received_by TEXT
);
CREATE TABLE contracts (
  id TEXT PRIMARY KEY, vendor_id TEXT NOT NULL, title TEXT, pdf_path TEXT,
  effective_start TEXT, effective_end TEXT, terms_json TEXT
);
CREATE TABLE bills (
  id TEXT PRIMARY KEY, vendor_id TEXT NOT NULL, po_id TEXT, invoice_number TEXT,
  invoice_date TEXT, due_date TEXT, amount_cents INTEGER, status TEXT, match_status TEXT,
  ramp_flag TEXT, pdf_path TEXT, vendor_notes TEXT, supersedes TEXT, paid_on TEXT,
  created_at TEXT
);
CREATE TABLE bill_lines (
  id TEXT PRIMARY KEY, bill_id TEXT NOT NULL, line_no INTEGER, po_line_id TEXT, sku TEXT,
  description TEXT, quantity INTEGER, unit_price_cents INTEGER, amount_cents INTEGER
);

-- Matchbook-owned state
CREATE TABLE cases (
  id TEXT PRIMARY KEY, bill_id TEXT NOT NULL UNIQUE, scenario TEXT, source TEXT,
  state TEXT NOT NULL, root_cause TEXT, playbook TEXT, variance_cents INTEGER DEFAULT 0,
  at_stake_cents INTEGER DEFAULT 0, diagnosis_json TEXT, variance_json TEXT,
  run_status TEXT DEFAULT 'idle', sim_day INTEGER DEFAULT 0,
  tokens_in INTEGER DEFAULT 0, tokens_out INTEGER DEFAULT 0,
  started_at TEXT, drafted_at TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE case_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL, ts TEXT, kind TEXT,
  title TEXT, data_json TEXT
);
CREATE TABLE drafts (
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL, recipient_type TEXT, recipient TEXT,
  subject TEXT, body_template TEXT, body TEXT, variables_json TEXT, validation_json TEXT,
  created_at TEXT
);
CREATE TABLE approvals (
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL, draft_id TEXT, bill_id TEXT, status TEXT,
  approver TEXT, requested_at TEXT, decided_at TEXT, note TEXT
);
CREATE TABLE messages (
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL, direction TEXT, sender TEXT, recipient TEXT,
  subject TEXT, body TEXT, attachment_bill_id TEXT, sim_day INTEGER, ts TEXT
);

-- Append-only: the audit log can only grow.
CREATE TRIGGER case_events_no_update BEFORE UPDATE ON case_events
BEGIN SELECT RAISE(ABORT, 'case_events is append-only'); END;
CREATE TRIGGER case_events_no_delete BEFORE DELETE ON case_events
BEGIN SELECT RAISE(ABORT, 'case_events is append-only'); END;
