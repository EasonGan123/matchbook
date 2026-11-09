"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Masthead } from "@/components/Masthead";
import { ContractsExhibit, CorrectionMark, DocumentsExhibit, CorrespondenceExhibit, DiagnosisExhibit, DraftExhibit, SyncedStamp, VarianceExhibit, correctionFor } from "@/components/Exhibits";
import { StateRail, StatusMark } from "@/components/StatusMark";
import { Trace } from "@/components/Trace";
import { API, get, post, usd, type CaseDetail, type CaseEvent } from "@/lib/api";
import { useTheme, useViewMode } from "@/lib/viewMode";

const REFRESH_ON = new Set(["state", "diagnosis", "draft", "engine", "validator", "approval", "message", "sync", "escalation", "reply", "ramp", "nudge", "plan"]);

function Button({ children, onClick, kind = "primary", disabled }: { children: React.ReactNode; onClick?: () => void; kind?: "primary" | "ghost" | "red"; disabled?: boolean }) {
  const ramp = useTheme() === "ramp";
  const styles = ramp
    ? {
        primary: "rounded-[6px] bg-solar text-ink hover:brightness-95",
        red: "rounded-[6px] bg-solar text-ink hover:brightness-95",
        ghost: "rounded-[6px] border border-hair bg-paper text-ink hover:bg-paper-2",
      }[kind]
    : {
        primary: "bg-ink text-paper hover:bg-red",
        red: "bg-red text-paper hover:bg-ink",
        ghost: "border border-ink text-ink hover:border-red hover:text-red",
      }[kind];
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`group inline-flex items-center gap-3 px-5 py-3 font-mono text-[12px] uppercase tracking-[0.1em] transition-colors duration-300 disabled:cursor-not-allowed disabled:opacity-40 ${styles}`}
    >
      {children}
    </button>
  );
}

export default function CasePage() {
  const { id } = useParams<{ id: string }>();
  const [d, setD] = useState<CaseDetail | null>(null);
  const [events, setEvents] = useState<CaseEvent[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const lastId = useRef(0);
  const detailed = useViewMode() === "detailed";
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const x = await get<CaseDetail>(`/api/cases/${id}`);
      setD(x);
      setErr(null);
      return x;
    } catch (e) {
      setErr(String(e));
    }
  }, [id]);

  const scheduleRefresh = useCallback(() => {
    if (refreshTimer.current) clearTimeout(refreshTimer.current);
    refreshTimer.current = setTimeout(load, 120);
  }, [load]);

  // Initial load, then follow the audit log over SSE.
  useEffect(() => {
    let es: EventSource | null = null;
    let cancelled = false;
    load().then((x) => {
      if (!x || cancelled) return;
      setEvents(x.events);
      lastId.current = x.events.at(-1)?.id ?? 0;
      es = new EventSource(`${API}/api/cases/${id}/stream?after=${lastId.current}`);
      es.addEventListener("case_event", (m) => {
        const e: CaseEvent = JSON.parse((m as MessageEvent).data);
        if (e.id <= lastId.current) return;
        lastId.current = e.id;
        setEvents((prev) => [...prev, e]);
        if (REFRESH_ON.has(e.kind)) scheduleRefresh();
      });
    });
    const onReset = () => window.location.reload();
    window.addEventListener("matchbook:reset", onReset);
    return () => {
      cancelled = true;
      es?.close();
      window.removeEventListener("matchbook:reset", onReset);
    };
  }, [id, load, scheduleRefresh]);

  // Fallback poll while something is running (covers a dropped stream).
  useEffect(() => {
    if (d?.case.run_status !== "running") return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [d?.case.run_status, load]);

  const act = async (name: string, path: string, body: object = {}) => {
    setBusy(name);
    setErr(null);
    try {
      await post(path, body);
      await load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(null);
    }
  };

  if (!d) {
    return (
      <>
        <Masthead section="Exhibit 02 / The case" />
        <div className="mt-24 font-mono text-[12px] text-muted">{err ? <span className="text-red">{err}</span> : "Loading case…"}</div>
      </>
    );
  }

  const c = d.case;
  const running = c.run_status === "running";
  const history = events.filter((e) => e.kind === "state").map((e) => e.data?.to).filter(Boolean);
  const correction = correctionFor(d);
  const escalation = [...events].reverse().find((e) => e.kind === "escalation");
  const approveLabel = c.playbook === "approve_with_note" ? "Approve bill" : c.playbook === "reject_duplicate" ? "Approve rejection" : "Approve & send";

  const approval =
    c.state === "PENDING_APPROVAL" ? (
      <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-hair pt-6">
        <Button kind="red" onClick={() => act("approve", `/api/cases/${id}/approve`, { approver: "Alex Rivera, Controller" })} disabled={!!busy}>
          {busy === "approve" ? "Approving…" : approveLabel}
          <span className="transition-transform group-hover:translate-x-1">→</span>
        </Button>
        <Button kind="ghost" onClick={() => act("reject", `/api/cases/${id}/reject`, { approver: "Alex Rivera, Controller" })} disabled={!!busy}>
          Reject, I&apos;ll handle it
        </Button>
        <span className="font-mono text-[11px] text-muted">Nothing leaves the building without your sign-off.</span>
      </div>
    ) : null;

  return (
    <>
      <Masthead section={`Exhibit 02 / ${c.id}`} />

      {/* ---------------------------------------------------------- title block */}
      <section className="mt-10 grid gap-10 md:mt-14 lg:grid-cols-[minmax(0,1fr)_400px] lg:items-end">
        <div className="min-w-0">
          <div className="flex items-center gap-4 font-mono text-[11px] uppercase tracking-[0.08em] text-muted">
            <Link href="/" className="hover:text-red">← Inbox</Link>
            <span className="text-faint">/</span>
            <span>{c.id}</span>
            <span className="text-faint">/</span>
            <StatusMark state={c.state} running={running} />
          </div>
          <motion.h1
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
            className="mt-5 font-serif text-[54px] leading-[0.95] tracking-[-0.01em] md:text-[92px]"
          >
            {d.bill.vendor.name}
          </motion.h1>
          <div className="mt-5 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[12px] text-ink-2">
            <a href={`${API}/fixtures/${d.bill.pdf_path}`} target="_blank" rel="noreferrer" className="underline decoration-hair underline-offset-2 hover:text-red">
              {d.bill.invoice_number} ↗
            </a>
            <span>{d.bill.invoice_date}</span>
            <span>{d.po?.number}</span>
            <span className="tabular">{usd(d.bill.amount_cents)}</span>
          </div>
          <p className="mt-3 max-w-[70ch] text-[14px] text-muted">
            {c.source === "contract_sweep" ? (
              <>
                <span className="text-red">Not flagged by Ramp:</span> invoice and PO agree, so three-way match passed. Matchbook&apos;s contract sweep caught it.
              </>
            ) : (
              <>
                <span className="text-ink">Ramp blocked this bill:</span> {d.bill.ramp_flag}.
              </>
            )}
          </p>
        </div>
        <div className="min-h-[170px] lg:justify-self-end">
          <AnimatePresence>{correction && <CorrectionMark key={correction.to} c={correction} />}</AnimatePresence>
        </div>
      </section>

      {/* ---------------------------------------------------------- rail + action */}
      <section className="mt-12">
        <StateRail state={c.state} history={history} />
        <div className="mt-8 flex min-h-[52px] flex-wrap items-center gap-4">
          {c.state === "OPEN" && !running && (
            <>
              <Button onClick={() => act("run", `/api/cases/${id}/run`)} disabled={!!busy}>
                Run Matchbook <span className="transition-transform group-hover:translate-x-1">→</span>
              </Button>
              <span className="max-w-[56ch] text-[13px] text-muted">
                Reads the bill, PO, receipts and contracts, computes the variance in code, and drafts the fix for your approval.
              </span>
            </>
          )}
          {running && (
            <span className="flex items-center gap-3 font-mono text-[12px] uppercase tracking-[0.08em] text-ink">
              <span className="pulse-dot inline-block h-2 w-2 rounded-full bg-red" />
              {c.state === "AWAITING_VENDOR" ? "Advancing the clock…" : "Matchbook is working"}
            </span>
          )}
          {c.state === "PENDING_APPROVAL" && (
            <a href="#draft" className="font-mono text-[12px] uppercase tracking-[0.08em] text-red">
              ● Ready for your approval ↓
            </a>
          )}
          {c.state === "AWAITING_VENDOR" && !running && (
            <>
              <Button onClick={() => act("ff", `/api/cases/${id}/fast-forward`)} disabled={!!busy}>
                Fast-forward follow-up <span>⟫</span>
              </Button>
              <span className="text-[13px] text-muted">Sent on day 0. Matchbook follows up every 3 days until the counterparty replies.</span>
            </>
          )}
          {c.state === "SYNCED" && <SyncedStamp label={d.bill.status === "rejected" ? "Rejected · synced to Ramp" : "Synced to Ramp"} />}
          {c.state === "ESCALATED" && escalation && (
            <div className="max-w-[80ch] border-l-2 border-red pl-4">
              <div className="label !text-red">Handed to a person</div>
              <p className="mt-1 font-serif text-[20px] leading-snug">{escalation.data?.reason}</p>
            </div>
          )}
          {err && <span className="font-mono text-[12px] text-red">{err}</span>}
        </div>
      </section>

      {/* ---------------------------------------------------------- body */}
      <section className="mt-16 grid gap-14 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="min-w-0 lg:sticky lg:top-8 lg:max-h-[calc(100vh-4rem)] lg:self-start lg:overflow-y-auto lg:pr-2">
          <Trace events={events} live={running} />
        </div>
        <div className="min-w-0">
          {c.variance && c.state !== "OPEN" && <VarianceExhibit d={d} />}
          {c.variance && c.state !== "OPEN" && d.contracts.length > 0 && <ContractsExhibit d={d} />}
          {c.diagnosis && <DiagnosisExhibit d={d} />}
          <div id="draft" />
          {d.draft && <DraftExhibit d={d} actions={approval} />}
          {(d.messages.length > 0 || c.sim_day > 0) && <CorrespondenceExhibit d={d} />}
          {!c.variance && !running && c.state === "OPEN" && <Placeholder />}
          {detailed && c.state !== "OPEN" && <DocumentsExhibit d={d} />}
        </div>
      </section>
    </>
  );
}

function Placeholder() {
  const steps = [
    { n: "01", t: "Read", s: "bill, PO, receipts, contracts", who: "Claude" },
    { n: "02", t: "Compute", s: "exact variance", who: "Code" },
    { n: "03", t: "Diagnose", s: "root cause + citations", who: "Claude" },
    { n: "04", t: "Approve", s: "nothing sent without you", who: "You", red: true },
  ];
  return (
    <div className="border-t border-ink pt-6">
      <div className="label">What happens next</div>
      <ol className="mt-6 grid grid-cols-2 gap-y-8 md:grid-cols-4">
        {steps.map((x, i) => (
          <li key={x.n} className="relative pr-4">
            {i < steps.length - 1 && <span className="absolute right-4 top-[18px] hidden h-px w-[calc(100%-56px)] bg-hair md:block" />}
            <span className={`flex h-9 w-9 items-center justify-center rounded-full font-mono text-[11px] ${x.red ? "bg-red text-paper" : "bg-ink text-paper"}`}>{x.n}</span>
            <div className="mt-3 font-serif text-[28px] leading-none">{x.t}</div>
            <div className="mt-1.5 text-[12.5px] text-muted">{x.s}</div>
            <div className={`mt-2 font-mono text-[10px] uppercase tracking-[0.08em] ${x.red ? "text-red" : "text-faint"}`}>{x.who}</div>
          </li>
        ))}
      </ol>
    </div>
  );
}
