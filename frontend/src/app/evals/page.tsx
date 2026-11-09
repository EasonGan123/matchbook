"use client";

import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { Masthead } from "@/components/Masthead";
import { get, post, rootLabel, usd } from "@/lib/api";
import { useTheme, useViewMode } from "@/lib/viewMode";

type Row = {
  n: number;
  title: string;
  setup: string;
  case_id: string;
  pass: boolean;
  checks: Record<string, boolean>;
  expected: { root_cause: string; playbook: string; amount_cents: number; is_dispute: boolean };
  got: { root_cause: string | null; playbook: string | null; amount_cents: number; state_after_run: string };
  seconds_to_draft: number | null;
  tokens_in: number;
  tokens_out: number;
};
type Result = {
  ran_at: string;
  mode: string;
  model: string | null;
  metrics: {
    cases_passed: number;
    cases: number;
    root_cause_accuracy: number;
    amount_exact_match: number | null;
    false_dispute_rate: number;
    median_seconds_to_draft: number | null;
    tokens_per_case: number | null;
  };
  rows: Row[];
};

const PLAYBOOK: Record<string, string> = {
  credit_memo_request: "Credit memo request",
  corrected_bill_request: "Corrected invoice request",
  receipt_confirmation: "Ask buyer to confirm receipt",
  reject_duplicate: "Reject duplicate",
  buyer_review: "Buyer approves or disputes",
  approve_with_note: "Approve with note",
  escalate: "Escalate to a person",
};

const CHECKS: { key: string; label: string; tip: string; get: (c: Record<string, boolean>) => boolean | null }[] = [
  { key: "rc", label: "Cause", tip: "Root cause matches", get: (c) => c.root_cause },
  { key: "pb", label: "Action", tip: "Playbook matches", get: (c) => c.playbook },
  { key: "amt", label: "Math", tip: "Variance exact to the cent", get: (c) => c.amount },
  { key: "cite", label: "Cites", tip: "Required evidence cited", get: (c) => c.citations },
  { key: "draft", label: "Draft", tip: "Draft passed number validation", get: (c) => ("draft_validated" in c ? c.draft_validated && (c.draft_amount_exact ?? true) : null) },
  { key: "guard", label: "Guard", tip: "Prompt injection flagged", get: (c) => ("injection_flagged" in c ? c.injection_flagged : null) },
  { key: "loop", label: "Closed", tip: "Approved, followed up, re-matched and synced; or correctly escalated", get: (c) => ("closed_loop" in c ? c.closed_loop : c.state) },
];

const pct = (x: number | null) => (x == null ? "—" : `${Math.round(x * 100)}%`);

export default function Evals() {
  const [res, setRes] = useState<Result | null>(null);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    get<{ data: Result | null }>("/api/evals").then((r) => setRes(r.data)).catch((e) => setErr(String(e)));
  }, []);

  const run = async () => {
    setRunning(true);
    setErr(null);
    try {
      const r = await post<{ data: Result }>("/api/evals/run");
      setRes(r.data);
    } catch (e) {
      setErr(String(e));
    } finally {
      setRunning(false);
    }
  };

  const m = res?.metrics;
  const scripted = res?.mode === "replay-scripted";
  const detailed = useViewMode() === "detailed";
  const theme = useTheme();

  return (
    <>
      <Masthead section="Exhibit 03 / The proof" />

      <section className="mt-16 grid gap-8 md:mt-24 lg:grid-cols-[1fr_auto] lg:items-end">
        <motion.h1
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
          className="font-serif text-[52px] leading-[0.98] md:text-[96px]"
        >
          Nine cases.
          <br />
          {m ? (
            m.cases_passed === m.cases ? (
              <>
                <em className="text-red">All</em> handled correctly.
              </>
            ) : (
              <>
                <em className="text-red">{m.cases_passed}</em> handled correctly.
              </>
            )
          ) : (
            <span className="text-faint">Not yet run.</span>
          )}
        </motion.h1>
        <div className="flex flex-col items-start gap-3 lg:items-end">
          <button
            onClick={run}
            disabled={running}
            className={`inline-flex items-center gap-3 px-5 py-3 font-mono text-[12px] uppercase tracking-[0.1em] transition-colors disabled:opacity-50 ${
              theme === "ramp" ? "rounded-[6px] bg-solar text-ink hover:brightness-95" : "bg-ink text-paper hover:bg-red"
            }`}
          >
            {running ? (
              <>
                <span className="pulse-dot inline-block h-2 w-2 rounded-full bg-paper" /> Running nine cases…
              </>
            ) : (
              <>Run the eval →</>
            )}
          </button>
          {res && (
            <div className="label">
              {new Date(res.ran_at).toLocaleString()} · {res.mode}
              {res.model ? ` · ${res.model}` : ""}
            </div>
          )}
        </div>
      </section>

      {scripted && (
        <div className="mt-10 border-l-2 border-red pl-4 text-[13.5px] leading-relaxed text-ink-2">
          <span className="label !text-red">Scripted responses · </span>
          This run replays hand-written model turns, so it checks the pipeline, the variance engine, the validator and the guardrails, not Claude&apos;s judgment.
          Set <span className="font-mono text-[12px]">ANTHROPIC_API_KEY</span> and run again for model metrics and real token counts.
        </div>
      )}
      {err && <div className="mt-6 font-mono text-[12px] text-red">{err}</div>}

      {m && (
        <section className="mt-14 grid grid-cols-2 border-t border-ink md:grid-cols-5">
          {[
            { label: "Root cause accuracy", v: pct(m.root_cause_accuracy) },
            { label: "Amounts exact", v: pct(m.amount_exact_match) },
            { label: "False disputes", v: pct(m.false_dispute_rate), red: true, sub: "Case 3 is the key test" },
            { label: "Median time to draft", v: m.median_seconds_to_draft == null ? "—" : `${m.median_seconds_to_draft}s`, sub: scripted ? "Pipeline only, no model latency" : "Blocked bill to draft" },
            { label: "Tokens per case", v: m.tokens_per_case == null ? "n/a" : m.tokens_per_case.toLocaleString(), sub: m.tokens_per_case == null ? "Live runs only" : undefined },
          ].map((s, i) => (
            <div key={s.label} className={`border-b border-hair py-5 md:border-b-0 ${i ? "md:border-l md:border-hair md:pl-6" : ""} ${i % 2 ? "pl-5" : ""}`}>
              <div className="label">{s.label}</div>
              <div className={`mt-3 font-serif text-[46px] leading-none tabular md:text-[56px] ${s.red ? "italic text-red" : ""}`}>{s.v}</div>
              {s.sub && <div className="mt-2 font-mono text-[10.5px] text-muted">{s.sub}</div>}
            </div>
          ))}
        </section>
      )}

      {res && (
        <section className="mt-16">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse">
              <thead>
                <tr className="border-b border-ink">
                  <th className="label w-10 pb-3 text-left font-normal">#</th>
                  <th className="label pb-3 text-left font-normal">Case</th>
                  {CHECKS.map((c) => (
                    <th key={c.key} className="label w-[78px] pb-3 text-center font-normal" title={c.tip}>{c.label}</th>
                  ))}
                  <th className="label w-[110px] pb-3 text-right font-normal">Amount</th>
                </tr>
              </thead>
              <tbody>
                {res.rows.map((r, i) => [
                  <motion.tr
                    key={r.n}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.1 + i * 0.04, duration: 0.4 }}
                    className="border-b border-hair"
                  >
                    <td className="py-4 align-middle font-mono text-[12px] text-muted">{String(r.n).padStart(2, "0")}</td>
                    <td className="py-4 pr-4 align-middle">
                      <div className="flex items-center gap-3">
                        <span className="font-serif text-[22px] leading-tight">{r.title}</span>
                        {r.got.state_after_run === "ESCALATED" && <span className="border border-red px-1.5 font-mono text-[9.5px] uppercase tracking-[0.06em] text-red">to a person</span>}
                        {r.expected.is_dispute === false && r.expected.playbook !== "escalate" && <span className="border border-ink/40 px-1.5 font-mono text-[9.5px] uppercase tracking-[0.06em] text-ink">no dispute</span>}
                      </div>
                      <div className="text-[12px] text-muted">{r.setup}</div>
                    </td>
                    {CHECKS.map((c) => {
                      const v = c.get(r.checks);
                      return (
                        <td key={c.key} className="text-center align-middle">
                          {v === null ? (
                            <span className="text-faint">·</span>
                          ) : v ? (
                            <span className="inline-block h-2.5 w-2.5 rounded-full bg-ink" title={`${c.label}: pass`} />
                          ) : (
                            <span className="font-mono text-[13px] font-semibold text-red" title={`${c.label}: fail`}>✗</span>
                          )}
                        </td>
                      );
                    })}
                    <td className="text-right align-middle font-mono text-[13px] tabular">{r.got.amount_cents ? usd(r.got.amount_cents) : "—"}</td>
                  </motion.tr>,
                  detailed ? (
                    <tr key={`${r.n}-detail`} className="border-b border-hair bg-paper-2/50">
                      <td />
                      <td colSpan={CHECKS.length + 2} className="py-3 pr-2">
                        <dl className="grid gap-x-6 gap-y-1 text-[12.5px] md:grid-cols-[90px_1fr_90px_1fr]">
                          <dt className="label">Expected</dt>
                          <dd className="text-ink-2">
                            <span className="font-mono text-[11px] text-ink">{r.expected.root_cause}</span> · {PLAYBOOK[r.expected.playbook]} · {usd(r.expected.amount_cents)}
                          </dd>
                          <dt className="label">Got</dt>
                          <dd className="text-ink-2">
                            <span className="font-mono text-[11px] text-ink">{r.got.root_cause ?? "—"}</span> · {PLAYBOOK[r.got.playbook ?? ""] ?? "—"} · {usd(r.got.amount_cents)}
                          </dd>
                          <dt className="label">Outcome</dt>
                          <dd className="text-ink-2">
                            {r.got.state_after_run}
                            {r.seconds_to_draft != null && ` · draft in ${r.seconds_to_draft}s`}
                            {res.mode === "live" && ` · ${(r.tokens_in + r.tokens_out).toLocaleString()} tokens`}
                          </dd>
                          <dt className="label">Checks</dt>
                          <dd className="font-mono text-[11px] text-muted">
                            {Object.entries(r.checks).map(([k, ok]) => (
                              <span key={k} className={`mr-3 ${ok ? "" : "text-red"}`}>{ok ? "✓" : "✗"} {k}</span>
                            ))}
                          </dd>
                        </dl>
                      </td>
                    </tr>
                  ) : null,
                ])}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-[12.5px] text-ink-2">
            <span className="flex items-center gap-2"><span className="inline-block h-2.5 w-2.5 rounded-full bg-ink" /> pass</span>
            <span className="flex items-center gap-2"><span className="font-mono text-[12px] font-semibold text-red">✗</span> fail</span>
            <span className="flex items-center gap-2"><span className="text-faint">·</span> not applicable</span>
          </div>
          {detailed && (
            <p className="mt-6 max-w-[90ch] text-[12.5px] leading-relaxed text-muted">
              Each case runs end to end against its own database: ingest, agent run, guardrails, draft validation, then approval, simulated follow-up, re-match and sync where
              the playbook calls for it. Cause, action, math and citations compare against fixtures/scenarios.json; amounts must match to the cent. Source: evals/run_evals.py ·
              results: evals/results/latest.json.
            </p>
          )}
        </section>
      )}

      <footer className="mt-24 flex flex-col justify-between gap-3 border-t border-hair pt-5 md:flex-row">
        <p className="font-serif text-[22px] italic text-ink-2">
          Ramp catches it. Matchbook <span className="text-red">closes</span> it.
        </p>
        <p className="label">{m ? `${m.cases_passed} of ${m.cases} passed` : ""}</p>
      </footer>
    </>
  );
}
