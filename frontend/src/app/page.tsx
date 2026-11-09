"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { useCallback, useEffect, useState } from "react";
import { Masthead } from "@/components/Masthead";
import { CountUp } from "@/components/marks";
import { StatusMark } from "@/components/StatusMark";
import { MagnitudeBar, QueueBar, queueGroup } from "@/components/Viz";
import { useTheme, useViewMode } from "@/lib/viewMode";
import { get, rootLabel, usd, usdShort, type CaseRow } from "@/lib/api";

const WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];
const DISPUTES = new Set(["credit_memo_request", "corrected_bill_request", "reject_duplicate"]);

export default function Inbox() {
  const [rows, setRows] = useState<CaseRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    get<{ data: CaseRow[] }>("/api/cases")
      .then((r) => {
        setRows(r.data);
        setErr(null);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 2500);
    window.addEventListener("matchbook:reset", load);
    return () => {
      clearInterval(t);
      window.removeEventListener("matchbook:reset", load);
    };
  }, [load]);

  const open = rows?.filter((r) => !["SYNCED", "ESCALATED"].includes(r.state)) ?? [];
  const atStake = open.reduce((s, r) => s + r.at_stake_cents, 0);
  const counts = (rows ?? []).reduce<Record<string, number>>((a, r) => ((a[queueGroup(r.state)] = (a[queueGroup(r.state)] ?? 0) + 1), a), {});
  const maxStake = Math.max(1, ...(rows ?? []).map((r) => r.at_stake_cents));
  const synced = rows?.filter((r) => r.state === "SYNCED") ?? [];
  const recovered = synced.filter((r) => DISPUTES.has(r.playbook ?? "")).reduce((s, r) => s + r.variance_cents, 0);
  const n = rows?.length ?? 0;
  const theme = useTheme();

  return (
    <>
      <Masthead section="Exhibit 01 / The queue" />

      <section className="mt-16 md:mt-24">
        <motion.h1
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
          className="font-serif text-[52px] leading-[0.98] tracking-[-0.01em] md:text-[96px]"
        >
          {theme === "ramp" ? (
            <span className="block text-[44px] md:text-[64px]">
              {rows && open.length === 0 ? "All exceptions closed" : <>Exceptions <span className="text-muted">{open.length}</span></>}
              <span className="mt-4 block max-w-[60ch] font-sans text-[16px] font-normal leading-relaxed tracking-normal text-muted md:text-[17px]" style={{ fontSizeAdjust: "none" }}>
                Bills blocked by three-way match. Matchbook finds the root cause, drafts the fix and follows up. You approve every action.
              </span>
            </span>
          ) : rows && open.length === 0 ? (
            <>
              Every exception is <em className="text-red">closed.</em>
            </>
          ) : (
            <>
              Ramp caught {WORDS[n] ?? n} exceptions.
              <br />
              Matchbook <em className="text-red">closes</em> them.
            </>
          )}
        </motion.h1>
      </section>

      <section className="mt-14 grid gap-10 border-t border-ink pt-6 md:mt-20 md:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)] md:gap-16">
        <div>
          <div className="label">Variance at stake</div>
          <div className="mt-3 font-serif text-[64px] italic leading-none text-red tabular md:text-[88px]">
            {rows ? <CountUp value={atStake} format={usdShort} /> : "—"}
          </div>
          {recovered > 0 && <div className="mt-3 font-mono text-[11.5px] text-ink">✓ {usd(recovered)} recovered so far</div>}
        </div>
        <div className="md:pt-1">
          <div className="label mb-4">Queue by status</div>
          <QueueBar counts={counts} />
        </div>
      </section>

      <section className="mt-16">
        <div className="hidden grid-cols-[88px_1.6fr_1.5fr_120px_130px_150px_20px] gap-4 border-b border-ink pb-3 md:grid">
          {["Case", "Vendor", "Issue", "Bill", "Variance", "Status", ""].map((h, i) => (
            <div key={i} className={`label ${i === 3 || i === 4 ? "text-right" : ""}`}>{h}</div>
          ))}
        </div>

        {err && (
          <div className="border-b border-hair py-8 font-mono text-[12px] text-red">
            Can&apos;t reach the Matchbook API at localhost:8000. Start it with <span className="text-ink">make dev</span>.
          </div>
        )}

        <ul>
          {rows?.map((r, i) => (
            <motion.li
              key={r.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 + i * 0.05, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            >
              <Link
                href={`/cases/${r.id}`}
                className="group grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 border-b border-hair py-5 transition-colors hover:bg-paper-2/70 md:grid-cols-[88px_1.6fr_1.5fr_120px_130px_150px_20px] md:items-center md:py-6"
              >
                <div className="order-3 font-mono text-[11px] text-muted md:order-none">{r.id}</div>
                <div className="order-1 md:order-none">
                  <div className="font-serif text-[26px] leading-tight md:text-[28px]">{r.vendor_name}</div>
                  <div className="font-mono text-[11px] text-muted">
                    {r.invoice_number} · {r.invoice_date}
                  </div>
                </div>
                <div className="order-4 col-span-2 text-[13.5px] leading-snug text-ink-2 md:order-none md:col-span-1">
                  <IssueTag r={r} />
                </div>
                <div className="order-5 hidden text-right font-mono text-[13px] tabular md:order-none md:block">{usd(r.amount_cents)}</div>
                <div className="order-2 text-right font-serif text-[26px] leading-none tabular md:order-none md:text-[30px]">
                  {r.at_stake_cents ? (
                    <span className={r.state === "OPEN" ? "text-faint" : ""}>{usd(r.variance_cents || r.at_stake_cents)}</span>
                  ) : (
                    <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-muted">no dispute</span>
                  )}
                  <MagnitudeBar value={r.at_stake_cents} max={maxStake} active={r.state !== "OPEN"} />
                </div>
                <div className="order-6 md:order-none">
                  <StatusMark state={r.state} running={r.run_status === "running"} />
                </div>
                <div className="hidden text-muted transition-transform duration-300 group-hover:translate-x-1 group-hover:text-red md:block">→</div>
              </Link>
            </motion.li>
          ))}
        </ul>
      </section>

      <footer className="mt-24 flex flex-col justify-between gap-3 border-t border-hair pt-5 md:flex-row">
        <p className="font-serif text-[22px] italic text-ink-2">Ramp catches it. Matchbook closes it.</p>
        <p className="label">Fictional vendors and figures · demo data</p>
      </footer>
    </>
  );
}

const FLAG_TAG: [RegExp, string][] = [
  [/price/i, "Price"],
  [/quantity/i, "Quantity"],
  [/receipt/i, "No receipt"],
  [/duplicate/i, "Duplicate"],
  [/not on PO/i, "Off-PO line"],
];

function IssueTag({ r }: { r: CaseRow }) {
  const detailed = useViewMode() === "detailed";
  const diagnosed = r.root_cause && r.state !== "OPEN";
  const sweep = r.source === "contract_sweep";
  const tag = diagnosed ? rootLabel[r.root_cause!] : sweep ? "Price vs contract" : FLAG_TAG.find(([re]) => re.test(r.ramp_flag ?? ""))?.[1] ?? "Flagged";
  const detail = diagnosed ? "diagnosed" : sweep ? "missed by three-way match" : (r.ramp_flag ?? "").match(/[\d.]+%/)?.[0] ? `${(r.ramp_flag ?? "").match(/[\d.]+%/)![0]} over PO` : "";
  return (
    <span className="flex flex-wrap items-center gap-2">
      <span className={`border px-1.5 py-0.5 font-mono text-[10.5px] uppercase tracking-[0.06em] ${sweep && !diagnosed ? "border-red text-red" : diagnosed ? "border-ink bg-ink text-paper" : "border-ink/40 text-ink"}`}>
        {tag}
      </span>
      {detail && <span className="text-[12.5px] text-muted">{detail}</span>}
      {detailed && (
        <span className="basis-full text-[12.5px] leading-snug text-ink-2">
          {sweep ? "Invoice and PO agree, so Ramp's three-way match passed; the PO price exceeds the contract." : r.ramp_flag}
          {r.playbook && r.state !== "OPEN" && <span className="text-muted"> · {r.playbook.replaceAll("_", " ")}</span>}
        </span>
      )}
    </span>
  );
}
