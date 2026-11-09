"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { get, post, type Meta } from "@/lib/api";
import { Matchstick } from "./marks";
import { setTheme, setViewMode, useTheme, useViewMode, type Theme, type ViewMode } from "@/lib/viewMode";

export function Masthead({ section }: { section: string }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [busy, setBusy] = useState(false);
  const view = useViewMode();
  const theme = useTheme();
  const path = usePathname();
  const router = useRouter();
  useEffect(() => {
    get<Meta>("/api/meta").then(setMeta).catch(() => setMeta(null));
  }, []);

  const reset = async () => {
    if (!confirm("Reset the demo to its seeded state?")) return;
    setBusy(true);
    await post("/api/admin/reset").finally(() => setBusy(false));
    router.push("/");
    router.refresh();
    window.dispatchEvent(new Event("matchbook:reset"));
  };

  const nav = (href: string, label: string) => {
    const on = href === "/" ? path === "/" || path.startsWith("/cases") : path.startsWith(href);
    return (
      <Link href={href} className={`transition-colors hover:text-ink ${on ? "text-ink" : "text-muted"}`}>
        {label}
      </Link>
    );
  };

  return (
    <header className="pt-9">
      <div className="grid grid-cols-[1fr_auto] items-center gap-4 font-mono text-[12px] uppercase tracking-[0.08em] md:grid-cols-3">
        <Link href="/" className="flex items-center gap-2.5 font-semibold text-ink">
          <Matchstick className="h-[22px] w-2 text-ink" />
          Matchbook
        </Link>
        <div className="hidden text-center text-muted md:block">{theme === "ramp" ? section.replace(/^Exhibit \S+ \/ /, "") : section}</div>
        <nav className="flex items-center justify-end gap-3 md:gap-5">
          {nav("/", "Inbox")}
          {nav("/evals", "Scorecard")}
          <button onClick={reset} disabled={busy} className="text-muted transition-colors hover:text-red disabled:opacity-40">
            Reset
          </button>
        </nav>
      </div>
      <div className={`mt-4 h-px ${theme === "ramp" ? "bg-hair" : "bg-ink"}`} />
      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-3 font-mono text-[10.5px] uppercase tracking-[0.08em] text-faint">
        <div className="flex items-center gap-3">
          <Segmented label="Level of detail" value={view} options={[["simple", "Simple"], ["detailed", "Detailed"]]} onChange={(v) => setViewMode(v as ViewMode)} />
          <Segmented label="Theme" value={theme} options={[["editorial", "Editorial"], ["ramp", "Ramp"]]} onChange={(v) => setTheme(v as Theme)} />
          <span className="hidden lg:inline">{meta?.company ?? "Northwind Manufacturing"} · Bill Pay</span>
        </div>
        <span className="flex items-center gap-2">
          {meta && (
            <>
              <span className={`inline-block h-1.5 w-1.5 rounded-full ${meta.mode === "live" ? "bg-red" : "bg-faint"}`} />
              {meta.mode === "live" ? `Live · ${meta.model}` : meta.mode === "replay-recorded" ? `Replay · recorded ${meta.model} runs` : "Replay · scripted responses"}
            </>
          )}
        </span>
      </div>
    </header>
  );
}

function Segmented({ label, value, options, onChange }: { label: string; value: string; options: [string, string][]; onChange: (v: string) => void }) {
  return (
    <div role="radiogroup" aria-label={label} className="flex overflow-hidden rounded-[3px] border border-ink/60 text-[10.5px]">
      {options.map(([v, text]) => (
        <button
          key={v}
          role="radio"
          aria-checked={value === v}
          onClick={() => onChange(v)}
          className={`px-2 py-[3px] uppercase tracking-[0.08em] transition-colors ${value === v ? "bg-ink text-paper" : "text-muted hover:text-ink"}`}
        >
          {text}
        </button>
      ))}
    </div>
  );
}
