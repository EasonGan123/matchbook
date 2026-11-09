export const API = process.env.NEXT_PUBLIC_API ?? "http://localhost:8000";

export async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export async function post<T = unknown>(path: string, body: unknown = {}): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? `${r.status}`);
  return r.json();
}

export const usd = (cents: number | null | undefined) => {
  if (cents == null) return "—";
  const neg = cents < 0;
  const c = Math.abs(Math.round(cents));
  return `${neg ? "−" : ""}$${Math.floor(c / 100).toLocaleString("en-US")}.${String(c % 100).padStart(2, "0")}`;
};

export const usdShort = (cents: number) => {
  const d = cents / 100;
  if (d >= 10000) return `$${(d / 1000).toFixed(1)}k`;
  return usd(cents).replace(/\.00$/, "");
};

export const qty = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString("en-US"));

export const rootLabel: Record<string, string> = {
  PRICE_ABOVE_CONTRACT: "Price above contract",
  QTY_EXCEEDS_RECEIPT: "Quantity over receipt",
  MISSING_RECEIPT: "Missing receipt",
  DUPLICATE_INVOICE: "Duplicate invoice",
  UNBUDGETED_CHARGE: "Unbudgeted charge",
  LEGITIMATE_CHANGE: "Legitimate change",
  UNKNOWN: "Unknown",
};

export const stateLabel: Record<string, string> = {
  OPEN: "Open",
  CONTEXT_GATHERED: "Gathering",
  DIAGNOSED: "Diagnosed",
  DRAFTED: "Drafted",
  PENDING_APPROVAL: "Needs approval",
  SENT: "Sent",
  AWAITING_VENDOR: "Awaiting reply",
  RESOLVED: "Resolved",
  SYNCED: "Synced",
  ESCALATED: "Escalated",
};

export type CaseRow = {
  id: string;
  bill_id: string;
  scenario: string | null;
  source: string;
  state: string;
  root_cause: string | null;
  playbook: string | null;
  variance_cents: number;
  at_stake_cents: number;
  run_status: string;
  invoice_number: string;
  invoice_date: string;
  amount_cents: number;
  ramp_flag: string | null;
  vendor_name: string;
};

export type CaseEvent = {
  id: number;
  case_id: string;
  ts: string;
  kind: string;
  title: string;
  data: any; // eslint-disable-line @typescript-eslint/no-explicit-any
};

export type Line = {
  id: string;
  line_no: number;
  sku: string;
  description: string;
  quantity: number;
  unit_price_cents: number;
  amount_cents: number;
  po_line_id?: string | null;
};

export type Bill = {
  id: string;
  invoice_number: string;
  invoice_date: string;
  due_date: string;
  amount_cents: number;
  status: string;
  match_status: string;
  ramp_flag: string | null;
  pdf_path: string;
  vendor_notes: string | null;
  po_id: string | null;
  lines: Line[];
  vendor: { id: string; name: string; contact_email: string };
};

export type Finding = {
  code: string;
  detail: string;
  amount_cents: number;
  formula: string;
  evidence: string[];
  sku: string | null;
  quantity: number | null;
  billed_unit_cents: number | null;
  expected_unit_cents: number | null;
  severity: string;
};

export type Variance = {
  findings: Finding[];
  lines: {
    bill_line_id: string;
    sku: string;
    description: string;
    quantity: number;
    billed_unit_cents: number;
    po_unit_cents: number | null;
    po_qty: number | null;
    contract_unit_cents: number | null;
    contract_ref: { contract_id: string; page: number; section: string; quote: string } | null;
    received_qty: number | null;
  }[];
  checks: string[];
  total_cents: number;
  clean: boolean;
};

export type Evidence = { id: string; label: string; kind: string; quote?: string; page?: number; contract_id?: string };

export type CaseDetail = {
  case: CaseRow & {
    diagnosis: {
      root_cause: string;
      evidence_ids: string[];
      summary: string;
      injection_detected: boolean;
      injection_flagged: boolean;
      problems: string[];
      evidence: Evidence[];
    } | null;
    variance: Variance | null;
    playbook_label: string | null;
    sim_day: number;
    tokens_in: number;
    tokens_out: number;
  };
  bill: Bill;
  po: { id: string; number: string; buyer_name: string; buyer_email: string; issued_on: string; lines: Line[] } | null;
  receipts: { id: string; quantity: number; received_on: string }[];
  vendor: { name: string; contact_email: string; contact_name: string };
  contracts: { id: string; title: string; pdf_path: string; effective_start: string; effective_end: string; terms: { _source?: string } }[];
  corrected_bill: Bill | null;
  draft: {
    id: string;
    recipient_type: string;
    recipient: string;
    subject: string;
    body_template: string;
    body: string;
    variables: Record<string, string>;
    validation: { ok: boolean; summary: string; numbers: { text: string; source: string | null }[] };
  } | null;
  approvals: { id: string; status: string; approver: string; decided_at: string | null }[];
  messages: { id: string; direction: string; sender: string; recipient: string; subject: string; body: string; sim_day: number; attachment_bill_id: string | null }[];
  events: CaseEvent[];
};

export type Meta = { mode: string; model: string; states: string[]; company: string };
