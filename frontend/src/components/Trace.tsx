"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { useViewMode } from "@/lib/viewMode";
import { qty, rootLabel, stateLabel, usd, type CaseEvent } from "@/lib/api";

/* eslint-disable @typescript-eslint/no-explicit-any */
function toolSummary(name: string, o: any): string {
  if (!o || o.error) return o?.error ?? "";
  switch (name) {
    case "get_bill":
      return `${o.invoice_number} · ${o.lines.length} line${o.lines.length > 1 ? "s" : ""} · ${usd(o.amount_cents)}${o.vendor_supplied_text ? " · vendor notes attached" : ""}`;
    case "get_purchase_order":
      return `${o.number} · issued ${o.issued_on} · ${o.buyer_name}, ${o.department}`;
    case "list_item_receipts":
      return o.count ? `${o.count} receipt${o.count === 1 ? "" : "s"} · ${qty(o.receipts.reduce((s: number, r: any) => s + r.quantity, 0))} units received` : "No receipts recorded";
    case "search_contracts":
      return o.contracts.map((k: any) => `${k.contract_id} (${k.effective_start.slice(0, 7)} → ${k.effective_end.slice(0, 7)})`).join(" · ");
    case "get_vendor_history":
      return `${o.bills.length} bill${o.bills.length === 1 ? "" : "s"} on file · ${o.bills.filter((b: any) => b.status === "paid").length} paid`;
    case "compute_variances":
      return o.clean && !o.findings.length ? "Clean" : `${o.findings.length} finding${o.findings.length > 1 ? "s" : ""} · ${usd(o.total_cents)} disputed`;
    default:
      return "";
  }
}

function argText(input: Record<string, string>) {
  return Object.entries(input ?? {})
    .filter(([, v]) => v !== "")
    .map(([k, v]) => `${k}: "${v}"`)
    .join(", ");
}

function Item({ e }: { e: CaseEvent }) {
  const d = e.data ?? {};
  switch (e.kind) {
    case "model":
      return (
        <div>
          <div className="label mb-1">Claude</div>
          <p className="font-serif text-[19px] italic leading-snug text-ink-2">{e.title}</p>
        </div>
      );
    case "tool":
      return (
        <div className="font-mono text-[12px] leading-relaxed">
          <div className="break-words">
            <span className="text-red">{e.title}</span>
            <span className="text-muted">({argText(d.input)})</span>
          </div>
          <div className="flex justify-between gap-3 text-muted">
            <span className="min-w-0 break-words text-ink-2">↳ {toolSummary(e.title, d.output)}</span>
            <span className="shrink-0 text-faint">{d.ms}ms</span>
          </div>
        </div>
      );
    case "state":
      return (
        <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-muted">
          {d.from ? <>→ {stateLabel[d.to] ?? d.to}</> : e.title}
          {d.reason && <span className="normal-case tracking-normal text-faint"> · {d.reason}</span>}
        </div>
      );
    case "engine":
      return (
        <div className="font-mono text-[12px]">
          <div className="label mb-1 !text-ink">Variance engine · code</div>
          {(d.findings ?? []).length === 0 && <div className="text-ink-2">✓ {e.title}</div>}
          {(d.findings ?? []).map((f: any, i: number) => (
            <div key={i} className={f.severity === "info" ? "text-ink-2" : "text-red"}>
              {f.formula}
            </div>
          ))}
        </div>
      );
    case "diagnosis":
      return (
        <div>
          <div className="label mb-1">Diagnosis</div>
          <div className="font-mono text-[13px] font-medium uppercase tracking-[0.06em] text-red">{e.title}</div>
          <div className="text-[13px] text-ink-2">{rootLabel[e.title]} · {d.evidence_ids?.length ?? 0} citations</div>
        </div>
      );
    case "validator":
      return (
        <div className={`font-mono text-[12px] ${d.ok ? "text-ink" : "text-red"}`}>
          {d.ok ? "✓" : "✗"} {e.title}
        </div>
      );
    case "security":
      return (
        <div className="border-l-2 border-red bg-red-wash px-3 py-2">
          <div className="label !text-red">Guardrail</div>
          <div className="text-[13px] text-ink">{e.title}</div>
          {d.content && <div className="mt-1 font-serif text-[15px] italic text-ink-2">“{d.content}”</div>}
          {d.detail && <div className="mt-1 text-[12.5px] text-ink-2">{d.detail}</div>}
        </div>
      );
    case "escalation":
    case "error":
      return (
        <div className="text-[13px] text-red">
          <span className="label !text-red">{e.kind === "error" ? "Error" : "Escalated"} · </span>
          {d.reason ?? d.error ?? e.title}
        </div>
      );
    case "sync":
      return <div className="font-mono text-[12px] text-ink">✓ {e.title}</div>;
    case "plan":
      return (
        <div className="text-[13px]">
          <span className="label">Playbook · </span>
          <span className="text-ink">{e.title}</span>
          {d.recipient && <span className="text-muted"> → {d.recipient}</span>}
        </div>
      );
    case "run":
      return <div className="label">{e.title}</div>;
    default:
      return <div className="text-[13px] text-ink-2">{e.title}</div>;
  }
}

const DOT: Record<string, string> = {
  tool: "bg-red", model: "bg-ink", security: "bg-red", escalation: "bg-red", error: "bg-red",
  diagnosis: "bg-red", sync: "bg-ink", engine: "bg-ink",
};

type Step = { label: string; value?: string; tone?: "bad" | "ok" | "muted"; glyph: string };

/** One plain-language line per meaningful event; narration and state changes live in the full log. */
function toStep(e: CaseEvent): Step | null {
  const d = e.data ?? {};
  const o = d.output;
  switch (e.kind) {
    case "tool":
      switch (e.title) {
        case "get_bill": return { glyph: "▤", label: "Read the invoice", value: o?.amount_cents != null ? usd(o.amount_cents) : undefined };
        case "get_purchase_order": return { glyph: "▤", label: "Read the purchase order", value: o?.number };
        case "list_item_receipts": return { glyph: "▤", label: "Checked receipts", value: o?.count ? `${qty(o.receipts.reduce((a: number, r: any) => a + r.quantity, 0))} received` : "none", tone: o?.count ? undefined : "bad" };
        case "search_contracts": return { glyph: "§", label: "Searched contracts", value: o?.contracts ? `${o.contracts.length} on file` : undefined };
        case "get_vendor_history": return { glyph: "▤", label: "Checked vendor history", value: o?.bills ? `${o.bills.length} bill${o.bills.length === 1 ? "" : "s"}` : undefined };
        case "compute_variances": return { glyph: "=", label: "Computed the variance in code", value: o?.findings?.length ? usd(o.total_cents) : "clean", tone: o?.total_cents ? "bad" : "ok" };
      }
      return null;
    case "security": return e.title === "Prompt injection ignored" ? null : { glyph: "!", label: "Ignored an instruction in vendor text", tone: "bad" };
    case "diagnosis": return { glyph: "◆", label: `Diagnosed: ${rootLabel[e.title] ?? e.title}`, value: `${d.evidence_ids?.length ?? 0} citations`, tone: e.title === "UNKNOWN" ? "bad" : undefined };
    case "plan": return { glyph: "→", label: e.title };
    case "validator": return { glyph: d.ok ? "✓" : "✗", label: d.ok ? "Every number traced" : "Draft rejected by validator", value: `${d.numbers?.length ?? 0} numbers`, tone: d.ok ? "ok" : "bad" };
    case "draft": return { glyph: "✎", label: "Drafted the message", value: d.seconds_to_draft != null ? `${d.seconds_to_draft}s` : undefined };
    case "approval": return { glyph: "✓", label: e.title, tone: e.title.startsWith("Rejected") ? "bad" : "ok" };
    case "message": return { glyph: d.direction === "in" ? "↙" : "↗", label: d.direction === "in" ? "Reply received" : "Sent", value: e.title.split(": ").at(-1)?.replace(/^(Sent to |reply from )/, "") };
    case "nudge": return { glyph: "↻", label: `Day ${d.day}: automatic follow-up` };
    case "reply": return { glyph: "◆", label: e.title };
    case "engine": return e.title.startsWith("Re-match") ? { glyph: "=", label: "Re-matched the correction", value: e.title.endsWith("clean") ? "clean" : "still off", tone: e.title.endsWith("clean") ? "ok" : "bad" } : null;
    case "ramp": return { glyph: "▤", label: e.title };
    case "sync": return { glyph: "✓", label: "Clean bill synced back", tone: "ok" };
    case "escalation": return { glyph: "!", label: "Escalated to a person", tone: "bad" };
    case "error": return { glyph: "!", label: "Error", value: d.error, tone: "bad" };
    case "state": return d.from ? null : { glyph: "○", label: "Case opened", tone: "muted" };
    default: return null;
  }
}

function Steps({ events }: { events: CaseEvent[] }) {
  const steps = events.map((e) => ({ e, s: toStep(e) })).filter((x) => x.s) as { e: CaseEvent; s: Step }[];
  return (
    <ol className="mt-3">
      <AnimatePresence initial={false}>
        {steps.map(({ e, s }) => (
          <motion.li
            key={e.id}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
            className="grid grid-cols-[22px_1fr_auto] items-baseline gap-2 border-b border-hair/70 py-2.5"
          >
            <span className={`text-center font-mono text-[12px] ${s.tone === "bad" ? "text-red" : s.tone === "muted" ? "text-faint" : "text-ink"}`}>{s.glyph}</span>
            <span className={`text-[14px] leading-snug ${s.tone === "muted" ? "text-muted" : "text-ink"}`}>{s.label}</span>
            {s.value && (
              <span className={`max-w-[180px] truncate text-right font-mono text-[11.5px] tabular ${s.tone === "bad" ? "text-red" : "text-muted"}`}>{s.value}</span>
            )}
          </motion.li>
        ))}
      </AnimatePresence>
    </ol>
  );
}

export function Trace({ events, live }: { events: CaseEvent[]; live: boolean }) {
  const mode = useViewMode();
  const [full, setFull] = useState(mode === "detailed");
  useEffect(() => setFull(mode === "detailed"), [mode]);
  return (
    <div>
      <div className="flex items-center justify-between border-b border-ink pb-3">
        <div className="label flex items-center gap-2 !text-ink">
          Agent trace
          {live && <span className="pulse-dot inline-block h-1.5 w-1.5 rounded-full bg-red" />}
        </div>
        <div className="flex font-mono text-[10.5px] uppercase tracking-[0.08em]">
          {(["Steps", "Full log"] as const).map((m, i) => (
            <button
              key={m}
              onClick={() => setFull(i === 1)}
              className={`px-2 py-0.5 transition-colors ${full === (i === 1) ? "bg-ink text-paper" : "text-muted hover:text-ink"}`}
            >
              {m}
            </button>
          ))}
        </div>
      </div>
      {events.length === 0 && <p className="mt-4 text-[13px] text-muted">Nothing yet. Run Matchbook to start.</p>}
      {!full ? (
        <Steps events={events} />
      ) : (
        <ol className="relative mt-5">
          <div className="absolute bottom-2 left-[3px] top-2 w-px bg-hair" />
          <AnimatePresence initial={false}>
            {events.map((e) => (
              <motion.li
                key={e.id}
                layout="position"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                className="relative pb-5 pl-6"
              >
                <span className={`absolute left-0 top-[7px] h-[7px] w-[7px] rounded-full ${DOT[e.kind] ?? "border border-faint bg-paper"}`} />
                <Item e={e} />
              </motion.li>
            ))}
          </AnimatePresence>
          <li className="pl-6 font-mono text-[10.5px] text-faint">{events.length} events · append-only audit log</li>
        </ol>
      )}
    </div>
  );
}
