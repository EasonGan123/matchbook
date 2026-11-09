import { stateLabel } from "@/lib/api";

/** Case status as a small mono label with a dot. Red means a person is needed. */
export function StatusMark({ state, running }: { state: string; running?: boolean }) {
  const needsYou = state === "PENDING_APPROVAL" || state === "ESCALATED";
  const done = state === "SYNCED";
  return (
    <span
      className={`inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.08em] ${
        needsYou ? "text-red" : done ? "text-ink" : "text-muted"
      }`}
    >
      {done ? (
        <svg viewBox="0 0 12 12" className="h-3 w-3" aria-hidden>
          <path d="M2 6.5 L5 9 L10 3" fill="none" stroke="currentColor" strokeWidth="1.6" />
        </svg>
      ) : (
        <span
          className={`inline-block h-1.5 w-1.5 rounded-full ${needsYou ? "bg-red" : running ? "bg-ink pulse-dot" : "border border-current"}`}
        />
      )}
      {running && !needsYou ? "Working" : stateLabel[state] ?? state}
    </span>
  );
}

const RAIL = ["OPEN", "CONTEXT_GATHERED", "DIAGNOSED", "DRAFTED", "PENDING_APPROVAL", "SENT", "AWAITING_VENDOR", "RESOLVED", "SYNCED"];
const RAIL_LABEL: Record<string, string> = {
  OPEN: "Open", CONTEXT_GATHERED: "Context", DIAGNOSED: "Diagnosed", DRAFTED: "Drafted",
  PENDING_APPROVAL: "Approval", SENT: "Sent", AWAITING_VENDOR: "Follow-up", RESOLVED: "Resolved", SYNCED: "Synced",
};

/** The eight-stage pipeline as a ruled line, like a table header. */
export function StateRail({ state, history }: { state: string; history: string[] }) {
  const escalated = state === "ESCALATED";
  const reached = new Set(history);
  const idx = escalated ? Math.max(...history.map((s) => RAIL.indexOf(s))) : RAIL.indexOf(state);
  return (
    <div className="relative">
      <div className="grid grid-cols-9 gap-0">
        {RAIL.map((s, i) => {
          const past = i < idx || (i === idx && (s === "SYNCED" || escalated));
          const current = i === idx && !escalated && s !== "SYNCED";
          const skipped = i < idx && !reached.has(s);
          return (
            <div key={s} className="relative pt-4">
              <div
                className={`absolute left-0 right-0 top-0 h-[2px] origin-left transition-all duration-700 ease-[var(--ease-out-quint)] ${
                  past || current ? "scale-x-100 bg-ink" : "scale-x-100 bg-hair"
                } ${current ? "!bg-red" : ""}`}
              />
              <div
                className={`truncate pr-2 font-mono text-[10px] uppercase tracking-[0.08em] transition-colors md:text-[11px] ${
                  current ? "text-red" : past ? (skipped ? "text-faint line-through" : "text-ink") : "text-faint"
                }`}
              >
                {current && <span className="pulse-dot mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-red align-middle" />}
                {RAIL_LABEL[s]}
              </div>
            </div>
          );
        })}
      </div>
      {escalated && (
        <div className="mt-3 font-mono text-[11px] uppercase tracking-[0.08em] text-red">
          ↳ Escalated to a person after {RAIL_LABEL[RAIL[Math.max(idx, 0)]]?.toLowerCase()}
        </div>
      )}
    </div>
  );
}
