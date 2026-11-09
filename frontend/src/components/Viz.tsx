"use client";

import { motion } from "motion/react";
import { API, qty, usd, type CaseDetail } from "@/lib/api";

/*
 * Visual grammar: ink = agrees / fine, red = disputed or needs a person (always with ✗ or a label),
 * hair = not in play. Text stays in ink tones; red marks carry the status.
 */

const HATCH = "repeating-linear-gradient(135deg, var(--color-red) 0 3px, #c23a2dbb 3px 6px)";
const ease = [0.22, 1, 0.36, 1] as const;

/* ---------------------------------------------------------------- tiny helpers */

function Tip({ text, children, className = "relative", style }: { text: string; children: React.ReactNode; className?: string; style?: React.CSSProperties }) {
  return (
    <span className={`group/tip block ${className}`} style={style}>
      {children}
      <span className="pointer-events-none absolute bottom-[calc(100%+8px)] left-1/2 z-30 w-max max-w-[260px] -translate-x-1/2 bg-ink px-2.5 py-1.5 hidden font-mono text-[10.5px] leading-snug text-paper group-hover/tip:block">
        {text}
      </span>
    </span>
  );
}

const Swatch = ({ kind }: { kind: "ok" | "bad" | "muted" }) => (
  <span
    className="inline-block h-2.5 w-2.5 shrink-0 rounded-[2px]"
    style={{ background: kind === "ok" ? "var(--color-ink)" : kind === "bad" ? HATCH : "var(--color-hair)" }}
  />
);

/* ---------------------------------------------------------------- bill composition bar */

export function BillBar({ d }: { d: CaseDetail }) {
  const v = d.case.variance!;
  const total = d.bill.amount_cents;
  const f = v.findings[0];
  const disputed = Math.min(total, d.case.variance_cents || v.total_cents);
  let okLabel = "matches PO, receipt and contract";
  let badLabel = "overbilled";
  if (!f) okLabel = "clean";
  else if (f.code === "QTY_OVER_RECEIPT") badLabel = "billed but not delivered";
  else if (f.code === "NO_RECEIPT") badLabel = "held until receipt is confirmed";
  else if (f.code === "DUPLICATE_OF_PAID") badLabel = "already paid";
  else if (f.code === "LINE_NOT_ON_PO") badLabel = "not on the PO";
  else if (f.code === "CONTRACT_CONFLICT") { okLabel = "agrees with the PO"; badLabel = "depends on which contract governs"; }
  else if (f.code === "PRICE_MATCHES_CONTRACT") okLabel = "correct as billed under the contract";
  const ok = total - disputed;
  const okPct = (ok / total) * 100;
  return (
    <div>
      <div className="flex h-3.5 w-full gap-[2px]">
        {ok > 0 && (
          <Tip text={`${usd(ok)} · ${okLabel}`} className="relative h-full" style={{ width: `${okPct}%` }}>
            <motion.div
              initial={{ scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ duration: 0.8, ease }}
              className={`h-full w-full origin-left rounded-l-[4px] bg-ink ${disputed > 0 ? "" : "rounded-r-[4px]"}`}
            />
          </Tip>
        )}
        {disputed > 0 && (
          <Tip text={`${usd(disputed)} · ${badLabel}`} className="relative h-full flex-1" style={{ minWidth: 4 }}>
            <motion.div
              initial={{ scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ duration: 0.5, delay: 0.7, ease }}
              style={{ background: HATCH }}
              className={`h-full w-full origin-left rounded-r-[4px] ${ok > 0 ? "" : "rounded-l-[4px]"}`}
            />
          </Tip>
        )}
      </div>
      <div className="mt-2.5 flex flex-wrap justify-between gap-x-6 gap-y-1 text-[13px] text-ink-2">
        {ok > 0 && (
          <span className="flex items-center gap-2">
            <Swatch kind="ok" /> <span className="font-mono tabular text-ink">{usd(ok)}</span> {okLabel}
          </span>
        )}
        {disputed > 0 && (
          <span className="flex items-center gap-2">
            <Swatch kind="bad" /> <span className="font-mono tabular text-ink">{usd(disputed)}</span> {badLabel}
          </span>
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- the four-way match grid */

type Cell = { value: string; note?: string; state: "ok" | "bad" | "muted" | "neutral"; tip?: string };

function pricesOn(d: CaseDetail, sku: string) {
  const on = d.bill.invoice_date;
  const out: { contract: string; price: number; section: string }[] = [];
  for (const k of d.contracts) {
    if (!(k.effective_start <= on && on <= k.effective_end)) continue;
    for (const p of (k.terms as any).price_schedule ?? []) {
      if (p.sku === sku && p.effective_from <= on && on <= p.effective_to)
        out.push({ contract: k.id, price: p.unit_price_cents, section: p.ref.section });
    }
  }
  return out;
}

function CellView({ c }: { c: Cell }) {
  const color = c.state === "bad" ? "text-red" : c.state === "muted" ? "text-faint" : "text-ink";
  const body = (
    <div className={`py-3 ${c.state === "bad" ? "bg-red-wash" : ""} px-3`}>
      <div className={`flex items-baseline gap-1.5 font-serif text-[24px] leading-none tabular md:text-[26px] ${color}`}>
        {c.state === "bad" && <span className="font-mono text-[12px]">✗</span>}
        {c.state === "ok" && <span className="font-mono text-[11px] text-faint">✓</span>}
        {c.value}
      </div>
      {c.note && <div className={`mt-1 font-mono text-[10.5px] ${c.state === "bad" ? "text-red" : "text-muted"}`}>{c.note}</div>}
    </div>
  );
  return c.tip ? <Tip text={c.tip}>{body}</Tip> : body;
}

export function MatchGrid({ d }: { d: CaseDetail }) {
  const v = d.case.variance!;
  const receipts = d.receipts as { id: string; quantity: number; po_line_id?: string }[];
  const contractIds = Array.from(new Set(v.lines.flatMap((l) => pricesOn(d, l.sku).map((p) => p.contract))));
  const cols = [
    { k: "Invoice", id: d.bill.invoice_number },
    { k: "Purchase order", id: d.po?.number ?? "—" },
    { k: "Receipt", id: receipts.length ? receipts.map((r) => r.id).join(", ") : "none" },
    { k: "Contract", id: contractIds.length ? contractIds.join(" · ") : "—" },
  ];
  return (
    <div className="overflow-x-auto">
      <div className="min-w-[560px]">
        <div className="grid grid-cols-[110px_repeat(4,minmax(0,1fr))] gap-x-[2px] border-b border-hair pb-2">
          <div />
          {cols.map((c) => (
            <div key={c.k} className="px-3">
              <div className="label">{c.k}</div>
              <div className="truncate font-mono text-[10.5px] text-faint">{c.id}</div>
            </div>
          ))}
        </div>
        {v.lines.map((l) => {
          const prices = pricesOn(d, l.sku);
          const distinct = Array.from(new Set(prices.map((p) => p.price)));
          const conflict = distinct.length > 1;
          const contract = !conflict && prices[0] ? prices[0] : null;
          const ref = contract?.price ?? l.po_unit_cents;
          const onPo = l.po_unit_cents != null;
          const invPriceBad = !onPo || (conflict ? l.billed_unit_cents !== l.po_unit_cents : ref != null && l.billed_unit_cents > ref);
          const poStale = onPo && contract != null && l.po_unit_cents !== contract.price;
          const short = l.received_qty == null || l.quantity > l.received_qty;
          const price: Cell[] = [
            { value: usd(l.billed_unit_cents), state: invPriceBad ? "bad" : "ok", note: invPriceBad && ref != null && !conflict ? `+${usd(l.billed_unit_cents - ref)} / unit` : undefined },
            onPo
              ? { value: usd(l.po_unit_cents), state: poStale ? "bad" : "ok", note: poStale ? "stale price" : undefined }
              : { value: "—", state: "bad", note: "not on PO" },
            { value: "", state: "muted" },
            conflict
              ? { value: distinct.map((p) => usd(p)).join(" / "), state: "bad", note: `${prices.length} contracts disagree`, tip: prices.map((p) => `${p.contract} §${p.section}: ${usd(p.price)}`).join(" · ") }
              : contract
                ? { value: usd(contract.price), state: "neutral", note: `§${contract.section} · governs`, tip: `${contract.contract} §${contract.section}, in force on ${d.bill.invoice_date}` }
                : { value: "—", state: "muted" },
          ];
          const quantity: Cell[] = [
            { value: qty(l.quantity), state: short ? "bad" : "ok", note: short && l.received_qty != null ? `${qty(l.quantity - l.received_qty)} more than received` : undefined },
            onPo ? { value: qty(l.po_qty), state: "ok" } : { value: "—", state: "bad", note: "not on PO" },
            l.received_qty == null ? { value: "none", state: "bad", note: "nothing logged" } : { value: qty(l.received_qty), state: short ? "bad" : "ok" },
            { value: "", state: "muted" },
          ];
          return (
            <div key={l.bill_line_id} className="border-b border-hair py-2">
              <div className="flex items-baseline gap-3 px-1 pt-2">
                <span className="font-mono text-[11px] text-ink">{l.sku}</span>
                <span className="truncate text-[12.5px] text-muted">{l.description}</span>
              </div>
              {(
                [
                  ["Unit price", price],
                  ["Quantity", quantity],
                ] as const
              ).map(([label, cells]) => (
                <div key={label} className="grid grid-cols-[110px_repeat(4,minmax(0,1fr))] items-center gap-x-[2px]">
                  <div className="label px-1">{label}</div>
                  {cells.map((c, i) => (
                    <CellView key={i} c={c} />
                  ))}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- contract timeline */

const t = (s: string) => new Date(s + "T00:00:00Z").getTime();
const short = (s: string) => new Date(s + "T00:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

export function ContractTimeline({ d }: { d: CaseDetail }) {
  const sku = d.case.variance?.lines[0]?.sku ?? d.bill.lines[0]?.sku;
  const inv = d.bill.invoice_date;
  const po = d.po?.issued_on;
  const rows = d.contracts.map((k) => {
    const entries = ((k.terms as any).price_schedule ?? []).filter((p: any) => p.sku === sku);
    return { k, entries };
  });
  const dates = [inv, ...(po ? [po] : []), ...d.contracts.flatMap((k) => [k.effective_start, k.effective_end])];
  const lo = Math.min(...dates.map(t));
  const hi = Math.max(...dates.map(t));
  const pad = (hi - lo) * 0.03;
  const x = (s: string) => ((t(s) - lo + pad) / (hi - lo + 2 * pad)) * 100;
  const years: number[] = [];
  for (let y = new Date(lo).getUTCFullYear() + 1; y <= new Date(hi).getUTCFullYear(); y++) years.push(y);
  const inForce = pricesOn(d, sku);
  const distinct = new Set(inForce.map((p) => p.price));

  return (
    <div>
      <div className="relative">
        {/* year grid */}
        <div className="pointer-events-none absolute inset-y-0 left-[150px] right-0 md:left-[190px]">
          {years.map((y) => (
            <div key={y} className="absolute inset-y-0 border-l border-hair/80" style={{ left: `${x(`${y}-01-01`)}%` }}>
              <span className="absolute -top-5 -translate-x-1/2 font-mono text-[10px] text-faint">{y}</span>
            </div>
          ))}
        </div>
        <div className="space-y-3 pt-6 pb-8">
          {rows.map(({ k, entries }) => {
            const active = inForce.some((p) => p.contract === k.id);
            return (
              <div key={k.id} className="grid grid-cols-[150px_1fr] items-center gap-3 md:grid-cols-[190px_1fr]">
                <a href={`${API}/fixtures/${k.pdf_path}`} target="_blank" rel="noreferrer" className="group min-w-0">
                  <div className={`line-clamp-2 text-[13px] leading-tight group-hover:text-red ${active ? "text-ink" : "text-muted"}`}>{k.title}</div>
                  <div className="font-mono text-[10px] text-faint">{k.id} ↗</div>
                </a>
                <div className="relative h-7">
                  <div
                    className="absolute top-1/2 h-px -translate-y-1/2 bg-hair"
                    style={{ left: `${x(k.effective_start)}%`, width: `${x(k.effective_end) - x(k.effective_start)}%` }}
                  />
                  {entries.map((p: any, i: number) => {
                    const live = p.effective_from <= inv && inv <= p.effective_to && k.effective_start <= inv && inv <= k.effective_end;
                    const bad = live && distinct.size > 1;
                    const left = x(p.effective_from);
                    const width = x(p.effective_to) - left;
                    return (
                      <Tip
                        key={i}
                        text={`${usd(p.unit_price_cents)} per ${p.unit} · ${p.effective_from} → ${p.effective_to} · §${p.ref.section}`}
                        className="absolute top-0 h-7"
                        style={{ left: `calc(${left}% + ${i ? 1 : 0}px)`, width: `calc(${width}% - ${i ? 2 : 0}px)` }}
                      >
                        <motion.div
                          initial={{ opacity: 0, scaleX: 0.6 }}
                          animate={{ opacity: 1, scaleX: 1 }}
                          transition={{ duration: 0.6, delay: 0.1 * i, ease }}
                          className={`flex h-full w-full origin-left items-center overflow-hidden rounded-[4px] px-2 font-mono text-[11px] tabular ${
                            live ? "text-paper" : "bg-paper-2 text-muted ring-1 ring-hair ring-inset"
                          }`}
                          style={{ background: live ? (bad ? HATCH : "var(--color-ink)") : undefined }}
                        >
                          {usd(p.unit_price_cents)}
                        </motion.div>
                      </Tip>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
        {/* markers */}
        <div className="pointer-events-none absolute inset-y-0 left-[162px] right-0 md:left-[202px]">
          <div className="absolute inset-y-1 w-[2px] -translate-x-1/2 bg-red" style={{ left: `${x(inv)}%` }}>
            <span className={`absolute -bottom-1 whitespace-nowrap bg-paper px-1 font-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-red ${x(inv) > 45 ? "right-2" : "left-2"}`}>
              Invoice · {short(inv)}
            </span>
          </div>
          {po && (
            <div className="absolute inset-y-4 w-0 -translate-x-1/2 border-l border-dashed border-ink" style={{ left: `${x(po)}%` }}>
              <span className="absolute -top-4 right-1 whitespace-nowrap font-mono text-[10px] uppercase tracking-[0.06em] text-ink-2">PO · {short(po)}</span>
            </div>
          )}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-[12.5px] text-ink-2">
        <span className="flex items-center gap-2"><Swatch kind="ok" /> price in force on the invoice date</span>
        <span className="flex items-center gap-2"><Swatch kind="muted" /> not in force</span>
        {distinct.size > 1 && <span className="flex items-center gap-2"><Swatch kind="bad" /> conflicting prices</span>}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- follow-up timeline */

export function FollowUpTimeline({ d }: { d: CaseDetail }) {
  const out = d.messages.find((m) => m.direction === "out");
  const reply = d.messages.find((m) => m.direction === "in");
  const nudges = d.events.filter((e) => e.kind === "nudge").map((e) => e.data.day as number);
  const synced = d.case.state === "SYNCED";
  const maxDay = Math.max(5, d.case.sim_day + 1);
  const pts: { day: number; label: string; kind: "out" | "nudge" | "in" | "done" }[] = [];
  if (out) pts.push({ day: 0, label: d.case.playbook === "reject_duplicate" ? "Notice sent" : "Request sent", kind: "out" });
  nudges.forEach((n) => pts.push({ day: n, label: "Follow-up", kind: "nudge" }));
  if (reply) pts.push({ day: reply.sim_day, label: reply.attachment_bill_id ? "Corrected invoice" : "Reply", kind: "in" });
  const pos = (day: number) => `${(day / maxDay) * 100}%`;
  return (
    <div>
      <div className="relative mx-2 mb-12 mt-12 h-6">
        <div className="absolute left-0 right-0 top-1/2 h-px bg-hair" />
        <motion.div
          className="absolute left-0 top-1/2 h-[2px] -translate-y-1/2 bg-ink"
          initial={{ width: 0 }}
          animate={{ width: pos(d.case.sim_day) }}
          transition={{ duration: 1, ease }}
        />
        {Array.from({ length: maxDay + 1 }, (_, i) => (
          <span key={i} className="absolute bottom-full mb-1 -translate-x-1/2 font-mono text-[9.5px] text-faint" style={{ left: pos(i) }}>
            {`D${i}`}
          </span>
        ))}
        {pts.map((p, i) => (
          <motion.div
            key={i}
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: 0.2 + i * 0.25, type: "spring", stiffness: 400, damping: 20 }}
            className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2"
            style={{ left: pos(p.day) }}
          >
            <span
              className={`block rounded-full ${
                p.kind === "nudge" ? "h-2.5 w-2.5 border-2 border-ink bg-paper" : p.kind === "in" ? "h-3.5 w-3.5 bg-red ring-2 ring-paper" : "h-3 w-3 bg-ink ring-2 ring-paper"
              }`}
            />
            <span className={`absolute left-1/2 top-[calc(100%+12px)] -translate-x-1/2 whitespace-nowrap text-[12px] ${p.kind === "in" ? "font-medium text-ink" : "text-ink-2"}`}>
              {p.label}
            </span>
          </motion.div>
        ))}
        {synced && reply && (
          <div className="absolute -top-9 -translate-x-1/2 whitespace-nowrap font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-ink" style={{ left: pos(reply.sim_day) }}>
            ✓ re-matched · synced
          </div>
        )}
      </div>
      {reply && (
        <div className="grid gap-4 border-l-2 border-ink pl-4 md:grid-cols-[1fr_auto] md:items-end">
          <p className="font-serif text-[19px] italic leading-snug text-ink-2">“{reply.body.split("\n")[0]}”</p>
          {reply.attachment_bill_id && d.corrected_bill && (
            <a
              href={`${API}/fixtures/${d.corrected_bill.pdf_path}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-3 self-start border border-hair bg-sheet px-3 py-2 font-mono text-[11.5px] hover:border-ink"
            >
              <span className="text-ink">{d.corrected_bill.invoice_number}</span>
              <span className="text-ink">{usd(d.corrected_bill.amount_cents)}</span>
              <span className="text-muted">↗</span>
            </a>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- inbox: queue by status */

export const QUEUE_GROUPS = [
  { key: "you", label: "Needs you", kind: "bad" as const },
  { key: "work", label: "In progress", kind: "work" as const },
  { key: "open", label: "Not started", kind: "muted" as const },
  { key: "done", label: "Closed", kind: "ok" as const },
];

export function queueGroup(state: string) {
  if (state === "PENDING_APPROVAL" || state === "ESCALATED") return "you";
  if (state === "OPEN") return "open";
  if (state === "SYNCED") return "done";
  return "work";
}

export function QueueBar({ counts }: { counts: Record<string, number> }) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  const bg = (k: string) =>
    k === "bad" ? HATCH : k === "ok" ? "var(--color-ink)" : k === "work" ? "var(--color-muted)" : "var(--color-hair)";
  return (
    <div>
      <div className="flex h-3.5 w-full gap-[2px]">
        {QUEUE_GROUPS.filter((g) => counts[g.key]).map((g, i, arr) => (
          <motion.div
            key={g.key}
            layout
            transition={{ duration: 0.6, ease }}
            className={`h-full ${i === 0 ? "rounded-l-[4px]" : ""} ${i === arr.length - 1 ? "rounded-r-[4px]" : ""}`}
            style={{ width: `${(counts[g.key] / total) * 100}%`, background: bg(g.kind) }}
            title={`${counts[g.key]} ${g.label.toLowerCase()}`}
          />
        ))}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 md:grid-cols-4">
        {QUEUE_GROUPS.map((g) => (
          <div key={g.key} className="flex items-center gap-2 text-[13px] text-ink-2">
            <span className="inline-block h-2.5 w-2.5 rounded-[2px]" style={{ background: bg(g.kind) }} />
            <span className="font-serif text-[22px] leading-none text-ink tabular">{counts[g.key] ?? 0}</span>
            {g.label}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- inbox: magnitude bar */

export function MagnitudeBar({ value, max, active }: { value: number; max: number; active: boolean }) {
  const pct = max ? Math.max(value > 0 ? 1.5 : 0, (value / max) * 100) : 0;
  return (
    <div className="mt-1.5 h-[5px] w-full rounded-full bg-hair/50">
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.9, ease }}
        className="h-full rounded-full"
        style={{ background: active ? "var(--color-red)" : "var(--color-faint)" }}
      />
    </div>
  );
}
