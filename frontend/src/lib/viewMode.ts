"use client";

import { useSyncExternalStore } from "react";
import { THEME_KEY } from "./themeBoot";

/** Simple (visual) vs Detailed (visual + full text). A per-viewer preference, kept in localStorage. */
export type ViewMode = "simple" | "detailed";

const KEY = "matchbook:view";
const EVENT = "matchbook:view";

function read(): ViewMode {
  try {
    return localStorage.getItem(KEY) === "detailed" ? "detailed" : "simple";
  } catch {
    return "simple";
  }
}

export function setViewMode(m: ViewMode) {
  try {
    localStorage.setItem(KEY, m);
  } catch {
    /* storage unavailable: the toggle still works for this page view */
    memo = m;
  }
  window.dispatchEvent(new Event(EVENT));
}

let memo: ViewMode | null = null;

function subscribe(cb: () => void) {
  window.addEventListener(EVENT, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(EVENT, cb);
    window.removeEventListener("storage", cb);
  };
}

export function useViewMode(): ViewMode {
  return useSyncExternalStore(subscribe, () => memo ?? read(), () => "simple");
}

/* ---------------------------------------------------------------- theme */
/** "editorial" (paper, serif, red pen) or "ramp" (Ramp's design language: white, warm grays, solar accent, sans). */
export type Theme = "editorial" | "ramp";

let themeMemo: Theme | null = null;

function readTheme(): Theme {
  try {
    return localStorage.getItem(THEME_KEY) === "ramp" ? "ramp" : "editorial";
  } catch {
    return "editorial";
  }
}

export function setTheme(t: Theme) {
  try {
    localStorage.setItem(THEME_KEY, t);
  } catch {
    themeMemo = t;
  }
  document.documentElement.dataset.theme = t;
  window.dispatchEvent(new Event(EVENT));
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, () => themeMemo ?? readTheme(), () => "editorial");
}
