"use client";

import { animate, motion, useInView, useMotionValue, useTransform } from "motion/react";
import { useEffect, useRef } from "react";

/** The logo: a single struck match. */
export function Matchstick({ lit = true, className = "" }: { lit?: boolean; className?: string }) {
  return (
    <svg viewBox="0 0 10 28" className={className} aria-hidden>
      <rect x="4.1" y="8" width="1.8" height="20" rx="0.6" fill="currentColor" />
      <ellipse cx="5" cy="5.6" rx="3.3" ry="4.6" fill={lit ? "var(--color-red)" : "currentColor"} />
    </svg>
  );
}

/** Hand-drawn ellipse that draws itself around corrected figures. */
export function PenCircle({ delay = 0.2, className = "" }: { delay?: number; className?: string }) {
  return (
    <svg viewBox="0 0 240 100" preserveAspectRatio="none" className={`pointer-events-none absolute ${className}`} aria-hidden>
      <motion.path
        d="M 44 18 C 92 2, 206 4, 228 40 C 244 70, 170 96, 104 92 C 38 88, 6 70, 12 46 C 18 24, 60 10, 138 9"
        fill="none"
        stroke="var(--color-red)"
        strokeWidth="2.6"
        strokeLinecap="round"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: 1, opacity: 1 }}
        transition={{ duration: 0.9, delay, ease: [0.65, 0, 0.35, 1] }}
      />
    </svg>
  );
}

/** Red pen strike through an incorrect figure. */
export function PenStrike({ delay = 0 }: { delay?: number }) {
  return (
    <svg viewBox="0 0 100 20" preserveAspectRatio="none" className="pointer-events-none absolute inset-x-[-6%] top-[38%] h-[30%] w-[112%]" aria-hidden>
      <motion.path
        d="M 2 12 C 30 9, 62 13, 98 7"
        fill="none"
        stroke="var(--color-red)"
        strokeWidth="2.4"
        vectorEffect="non-scaling-stroke"
        strokeLinecap="round"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.45, delay, ease: "easeOut" }}
      />
    </svg>
  );
}

/** Number that counts up when it scrolls into view. */
export function CountUp({ value, format }: { value: number; format: (n: number) => string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const mv = useMotionValue(0);
  const text = useTransform(mv, (v) => format(Math.round(v)));
  useEffect(() => {
    if (!inView) return;
    const c = animate(mv, value, { duration: 1.1, ease: [0.22, 1, 0.36, 1] });
    return () => c.stop();
  }, [inView, value, mv]);
  return <motion.span ref={ref}>{text}</motion.span>;
}
