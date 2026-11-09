"use client";

import { motion } from "motion/react";
import { Fragment, type ReactNode } from "react";
import { API, qty, rootLabel, usd, type CaseDetail, type Finding } from "@/lib/api";
import { PenCircle, PenStrike } from "./marks";
import { BillBar, ContractTimeline, FollowUpTimeline, MatchGrid } from "./Viz";
import { useTheme, useViewMode } from "@/lib/viewMode";

export function Exhibit({ letter, title, note, children, delay = 0 }: { letter: string; title: string; note?: string; children: ReactNode; delay?: number }) {
  const theme = useTheme();
  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
      className="mb-14"
    >
      <div className="flex items-baseline justify-between gap-4 border-b border-ink pb-3">
        {theme === "ramp" ? (
          <h2 className="text-[16px] font-semibold tracking-[-0.01em] text-ink">{title}</h2>
        ) : (
          <div className="label !text-ink">
            Exhibit {letter} <span className="text-faint">/</span> {title}
          </div>
        )}
        {note && <div className="label text-right">{note}</div>}
      </div>
      <div className="pt-6">{children}</div>
    </motion.section>
  );
}

/* ------------------------------------------------------------ the correction mark (top right) */

export function correctionFor(d: CaseDetail): { label: string; from: string; to: string; caption: string } | null {
  const v = d.case.variance;
  if (!v || d.case.state === "OPEN") return null;
  const f = v.findings[0];
  if (!f) return null;
  const line = v.lines.find((l) => l.sku === f.sku) ?? v.lines[0];
  const inv = d.bill.invoice_number.replace(/^INV-/, "INV ");
  const synced = d.case.state === "SYNCED";
  switch (f.code) {
    case "PRICE_ABOVE_CONTRACT":
    case "PO_ABOVE_CONTRACT":
      return { label: `${inv} / line 01 / unit price`, from: usd(f.billed_unit_cents), to: usd(f.expected_unit_cents),
               caption: synced ? "Corrected by Matchbook" : `Contract price · §${line?.contract_ref?.section ?? ""}` };
    case "QTY_OVER_RECEIPT":
      return { label: `${inv} / line 01 / quantity`, from: qty(line.quantity), to: qty(line.received_qty),
               caption: synced ? "Corrected by Matchbook" : "Received at the dock" };
    case "PRICE_MATCHES_CONTRACT":
      return { label: `${d.po?.number} / line 01 / unit price`, from: usd(line.po_unit_cents), to: usd(line.contract_unit_cents),
               caption: "PO is stale · bill is right" };
    case "DUPLICATE_OF_PAID":
      return { label: `${inv} / amount due`, from: usd(d.bill.amount_cents), to: "$0", caption: "Already paid" };
    default:
      return null;
  }
}

export function CorrectionMark({ c }: { c: NonNullable<ReturnType<typeof correctionFor>> }) {
  return (
    <div className="w-full max-w-[400px]">
      <div className="label border-b border-hair pb-3">{c.label}</div>
      <div className="flex items-center gap-6 py-5">
        <span className={`relative shrink-0 whitespace-nowrap font-mono text-ink-2 tabular ${c.from.length > 6 ? "text-[24px] md:text-[26px]" : "text-[30px] md:text-[34px]"}`}>
          {c.from}
          <PenStrike delay={0.3} />
        </span>
        <span className="relative shrink-0 whitespace-nowrap px-5 py-2">
          <PenCircle delay={0.7} className="inset-[-10%_-8%] h-[120%] w-[116%]" />
          <motion.span
            initial={{ opacity: 0, rotate: -3 }}
            animate={{ opacity: 1, rotate: -3 }}
            transition={{ delay: 0.55, duration: 0.5 }}
            className={`block font-serif italic leading-none text-red tabular ${c.to.length > 6 ? "text-[40px] md:text-[44px]" : "text-[48px] md:text-[56px]"}`}
          >
            {c.to}
          </motion.span>
        </span>
      </div>
      <div className="border-t border-hair pt-3 font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-red">{c.caption}</div>
    </div>
  );
}

/* ------------------------------------------------------------ A. the mismatch */

export function VarianceExhibit({ d }: { d: CaseDetail }) {
  const v = d.case.variance!;
  const f = v.findings[0];
  const [lhs, rhsFull] = (f?.formula ?? "").split(" = ");
  const rhs = rhsFull?.match(/^\S+/)?.[0];
  const info = f?.severity === "info";
  const detailed = useViewMode() === "detailed";
  return (
    <Exhibit letter="A" title="The mismatch" note="Computed in code, not by the model">
      {f ? (
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className="font-serif text-[28px] leading-tight text-ink-2 tabular md:text-[34px]">{lhs}</span>
          {rhs && <span className={`font-serif text-[46px] italic leading-none tabular md:text-[60px] ${info ? "text-ink" : "text-red"}`}>= {rhs}</span>}
        </div>
      ) : (
        <p className="font-serif text-[32px]">Clean. Nothing to dispute.</p>
      )}
      {info && <p className="mt-2 text-[14px] text-ink-2">Above the PO, but exactly what the contract allows. <span className="text-ink">Not a dispute.</span></p>}
      <div className="mt-7"><BillBar d={d} /></div>
      <div className="mt-9"><MatchGrid d={d} /></div>
      {detailed && <VarianceDetail d={d} />}
    </Exhibit>
  );
}

export function ContractsExhibit({ d }: { d: CaseDetail }) {
  return (
    <Exhibit letter="B" title="Which contract applied" note={`${d.contracts.length} on file`} delay={0.05}>
      <ContractTimeline d={d} />
    </Exhibit>
  );
}

/* ------------------------------------------------------------ C. diagnosis */

const KIND_LABEL: Record<string, string> = { bill: "Invoice", bill_line: "Invoice", po: "PO", po_line: "PO", receipt: "Receipt", contract: "Contract" };

export function DiagnosisExhibit({ d }: { d: CaseDetail }) {
  const dx = d.case.diagnosis!;
  const quotes = dx.evidence.filter((e) => e.kind === "contract" && e.quote);
  const detailed = useViewMode() === "detailed";
  return (
    <Exhibit letter="C" title="Diagnosis" delay={0.05}>
      <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div>
          <div className="font-mono text-[11px] font-medium uppercase tracking-[0.08em] text-red">{dx.root_cause}</div>
          <h3 className="mt-1 font-serif text-[40px] leading-[1.02]">{rootLabel[dx.root_cause]}</h3>
          <div className="mt-4 flex flex-wrap gap-1.5">
            {dx.evidence.map((ev) => (
              <span key={ev.id} title={ev.id} className="inline-flex items-center gap-1.5 border border-hair bg-sheet px-2 py-1 font-mono text-[10.5px] text-ink">
                <span className="text-muted">{KIND_LABEL[ev.kind] ?? ev.kind}</span>
                {ev.id.split("#")[1] ? (ev.kind === "contract" ? `§${ev.id.split("#")[1]}` : ev.id.split("#")[1]) : ev.id.split(":")[1]}
              </span>
            ))}
          </div>
        </div>
        <p className="font-serif text-[20px] leading-snug text-ink-2">{dx.summary}</p>
      </div>

      {dx.injection_flagged && (
        <div className="mt-6 flex gap-3 border-l-2 border-red bg-red-wash px-4 py-3">
          <span className="font-mono text-[14px] text-red">!</span>
          <div>
            <div className="label !text-red">Instruction in vendor text · ignored and logged</div>
            {d.bill.vendor_notes && <p className="mt-1 font-serif text-[16px] italic text-ink-2 line-through decoration-red/70">“{d.bill.vendor_notes}”</p>}
          </div>
        </div>
      )}

      {dx.problems?.length > 0 && (
        <ul className="mt-5 space-y-1 text-[13px] text-red">
          {dx.problems.map((p) => <li key={p}>✗ {p}</li>)}
        </ul>
      )}

      {quotes.map((ev) => (
        <figure key={ev.id} className="mt-7">
          <blockquote className="font-serif text-[22px] leading-snug">
            “<span className="mark">{ev.quote}</span>”
          </blockquote>
          <figcaption className="mt-1.5 font-mono text-[10.5px] text-muted">
            {ev.label} · p.{ev.page} ·{" "}
            <a href={`${API}/fixtures/pdf/${ev.contract_id}.pdf`} target="_blank" rel="noreferrer" className="underline decoration-hair underline-offset-2 hover:text-red">PDF ↗</a>
          </figcaption>
        </figure>
      ))}

      {detailed && (
        <Detail title="Evidence cited">
          <table className="w-full text-left">
            <tbody>
              {dx.evidence.map((ev) => (
                <tr key={ev.id} className="border-b border-hair/70 align-top">
                  <td className="py-2 pr-4 font-mono text-[11px] text-muted">{ev.id}</td>
                  <td className="py-2 pr-4 text-[13px] text-ink">{ev.label}</td>
                  <td className="py-2 text-right font-mono text-[11px] text-muted">{ev.page ? `p.${ev.page}` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-[12.5px] text-muted">
            Every id was returned by a tool during this run; the orchestrator escalates any citation the agent never retrieved.
          </p>
        </Detail>
      )}
    </Exhibit>
  );
}

/* ------------------------------------------------------------ C. draft */

const VAR = /\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}/g;

function Templated({ template, vars }: { template: string; vars: Record<string, string> }) {
  const out: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  VAR.lastIndex = 0;
  while ((m = VAR.exec(template))) {
    out.push(<Fragment key={k++}>{template.slice(last, m.index)}</Fragment>);
    const name = m[1];
    const isNumber = /\d/.test(vars[name] ?? "");
    out.push(
      <span
        key={k++}
        title={`{{${name}}} · filled by code`}
        className={isNumber ? "rounded-[2px] bg-red-wash px-[2px] text-ink underline decoration-red decoration-dotted underline-offset-[3px]" : ""}
      >
        {vars[name] ?? m[0]}
      </span>,
    );
    last = m.index + m[0].length;
  }
  out.push(<Fragment key={k++}>{template.slice(last)}</Fragment>);
  return <>{out}</>;
}

export function DraftExhibit({ d, actions }: { d: CaseDetail; actions?: ReactNode }) {
  const dr = d.draft!;
  const toController = dr.recipient_type === "controller";
  const nums = dr.validation.numbers ?? [];
  const detailed = useViewMode() === "detailed";
  return (
    <Exhibit letter="D" title={toController ? "Approval note" : `Draft to ${dr.recipient_type}`} note={d.case.playbook_label ?? undefined} delay={0.1}>
      <div className="bg-sheet px-6 py-6 shadow-[0_1px_0_#d8d1c4,0_18px_40px_-28px_#3b383340] md:px-9 md:py-8">
        <dl className="grid grid-cols-[70px_1fr] gap-y-1 font-mono text-[11.5px]">
          <dt className="text-muted">TO</dt>
          <dd className="text-ink">{dr.recipient}</dd>
          <dt className="text-muted">FROM</dt>
          <dd className="text-ink">ap@northwind-mfg.example</dd>
          <dt className="text-muted">SUBJECT</dt>
          <dd className="text-ink">
            {dr.subject}
          </dd>
        </dl>
        <div className="my-5 h-px bg-hair" />
        <div className="whitespace-pre-wrap text-[15px] leading-[1.7] text-ink">
          <Templated template={dr.body_template} vars={dr.variables} />
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div className={`font-mono text-[11.5px] ${dr.validation.ok ? "text-ink" : "text-red"}`}>
          {dr.validation.ok ? "✓" : "✗"} {dr.validation.summary}
        </div>
        <div className="font-mono text-[10.5px] text-faint">
          {nums.filter((n) => n.source === "variable").length} from engine · {nums.filter((n) => n.source === "evidence").length} from documents · 0 typed by the model
        </div>
      </div>
      {detailed && (
        <Detail title="Number trace">
          <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-x-6 md:grid-cols-[repeat(2,minmax(0,1fr))]">
            {Object.entries(dr.variables)
              .filter(([k]) => dr.body_template.includes(`{{${k}}}`) || dr.subject.includes(dr.variables[k]))
              .map(([k, val]) => (
                <div key={k} className="flex items-baseline justify-between gap-3 border-b border-hair/70 py-1.5">
                  <span className="font-mono text-[11px] text-muted">{`{{${k}}}`}</span>
                  <span className="truncate font-mono text-[11.5px] text-ink">{val}</span>
                </div>
              ))}
          </div>
          <p className="mt-3 text-[12.5px] text-muted">
            The model wrote the template; code filled every value from the variance engine and the records above. Template as written:
          </p>
          <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap bg-paper-2 p-3 font-mono text-[11px] leading-relaxed text-ink-2">{dr.body_template}</pre>
        </Detail>
      )}
      {actions}
    </Exhibit>
  );
}

/* ------------------------------------------------------------ E. follow-up */

export function CorrespondenceExhibit({ d }: { d: CaseDetail }) {
  return (
    <Exhibit letter="E" title="Follow-up" note={`Simulated day ${d.case.sim_day}`} delay={0.05}>
      <FollowUpTimeline d={d} />
      {useViewMode() === "detailed" && (
        <Detail title="Message thread">
          <div className="space-y-6">
            {d.messages.map((m) => (
              <div key={m.id} className={m.direction === "in" ? "border-l-2 border-ink pl-4" : ""}>
                <div className="font-mono text-[11px] text-muted">
                  DAY {m.sim_day} · {m.direction === "out" ? `to ${m.recipient}` : `from ${m.sender}`}
                </div>
                <div className="mt-0.5 text-[14px] font-medium text-ink">{m.subject}</div>
                <p className="mt-1.5 whitespace-pre-wrap text-[13.5px] leading-relaxed text-ink-2">{m.body}</p>
              </div>
            ))}
          </div>
        </Detail>
      )}
    </Exhibit>
  );
}

/* ------------------------------------------------------------ detailed-mode pieces */

function Detail({ title, children }: { title: string; children: ReactNode }) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }} className="mt-8 border-t border-dashed border-hair pt-5">
      <div className="label mb-3">{title}</div>
      {children}
    </motion.div>
  );
}

function VarianceDetail({ d }: { d: CaseDetail }) {
  const v = d.case.variance!;
  return (
    <Detail title="Engine findings">
      <ul className="space-y-3">
        {v.findings.map((f, i) => (
          <li key={i} className="grid gap-1 md:grid-cols-[200px_1fr] md:gap-4">
            <span className={`font-mono text-[11px] uppercase tracking-[0.06em] ${f.severity === "info" ? "text-ink" : "text-red"}`}>{f.code}</span>
            <span>
              <span className="block text-[13.5px] leading-relaxed text-ink-2">{f.detail}</span>
              <span className="block font-mono text-[11px] text-muted">{f.formula} · evidence {f.evidence.join(", ")}</span>
            </span>
          </li>
        ))}
      </ul>
      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[520px] font-mono text-[12px] tabular">
          <thead>
            <tr className="border-b border-hair text-left">
              {["Line", "SKU", "Billed qty", "PO qty", "Received", "Billed", "PO", "Contract"].map((h) => (
                <th key={h} className="label pb-2 pr-3 font-normal">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {v.lines.map((l) => (
              <tr key={l.bill_line_id} className="border-b border-hair/70">
                <td className="py-2 pr-3 text-muted">{l.bill_line_id}</td>
                <td className="pr-3">{l.sku}</td>
                <td className="pr-3">{qty(l.quantity)}</td>
                <td className="pr-3">{l.po_qty == null ? "—" : qty(l.po_qty)}</td>
                <td className="pr-3">{l.received_qty == null ? "none" : qty(l.received_qty)}</td>
                <td className="pr-3">{usd(l.billed_unit_cents)}</td>
                <td className="pr-3">{l.po_unit_cents == null ? "—" : usd(l.po_unit_cents)}</td>
                <td className="pr-3">
                  {l.contract_unit_cents == null ? "—" : usd(l.contract_unit_cents)}
                  {l.contract_ref && <span className="text-faint"> {l.contract_ref.contract_id} §{l.contract_ref.section}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="mt-4 space-y-0.5">
        {v.checks.map((c) => (
          <li key={c} className="font-mono text-[10.5px] text-muted">✓ {c}</li>
        ))}
      </ul>
    </Detail>
  );
}

export function DocumentsExhibit({ d }: { d: CaseDetail }) {
  const docs = [
    { href: d.bill.pdf_path, name: `Invoice ${d.bill.invoice_number}`, meta: d.bill.invoice_date },
    ...(d.corrected_bill ? [{ href: d.corrected_bill.pdf_path, name: `Corrected invoice ${d.corrected_bill.invoice_number}`, meta: d.corrected_bill.status }] : []),
    ...d.contracts.map((k) => ({ href: k.pdf_path, name: k.title, meta: `${k.effective_start} → ${k.effective_end}${k.terms?._source === "fixture-ground-truth" ? " · terms from fixture" : ""}` })),
  ];
  return (
    <Exhibit letter="F" title="Documents on file">
      <ul className="divide-y divide-hair">
        {docs.map((x) => (
          <li key={x.href}>
            <a href={`${API}/fixtures/${x.href}`} target="_blank" rel="noreferrer" className="group flex items-baseline justify-between gap-4 py-3">
              <span className="font-serif text-[20px] group-hover:text-red">{x.name}</span>
              <span className="font-mono text-[11px] text-muted">{x.meta} ↗</span>
            </a>
          </li>
        ))}
      </ul>
    </Exhibit>
  );
}

/* ------------------------------------------------------------ the stamp */

export function SyncedStamp({ label }: { label: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 1.6, rotate: -14 }}
      animate={{ opacity: 1, scale: 1, rotate: -7 }}
      transition={{ type: "spring", stiffness: 260, damping: 18, delay: 0.15 }}
      className="inline-block border-[2.5px] border-red px-4 py-2 font-mono text-[15px] font-semibold uppercase tracking-[0.14em] text-red mix-blend-multiply"
    >
      {label}
    </motion.div>
  );
}
