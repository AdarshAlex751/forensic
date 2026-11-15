import type { ContradictionKind } from "../../shared/types";

export const KIND_LABEL: Record<ContradictionKind, string> = {
  physical: "Physical",
  temporal: "Temporal",
  statement: "Statement",
  custody: "Custody",
};

/** "2026-03-04 18:16:10 -05:00": the timestamp exactly as the record states it (date, time, UTC offset). */
export function stamp(t: string | null | undefined): string {
  if (!t || t.length < 19) return "";
  return `${t.slice(0, 10)} ${t.slice(11, 19)} ${t.slice(19)}`.trim();
}

/** Seconds as "2460 s (41 min)"; only the arithmetic is ours, the number comes from the data. */
export function seconds(s: number): string {
  return s >= 120 ? `${Math.round(s)} s (${Math.round(s / 60)} min)` : `${Math.round(s)} s`;
}

export function score(v: number): string {
  return v.toFixed(2);
}

/** Enter/Space-safe helper for list rows that act as buttons. */
export const pct = (v: number) => `${Math.round(Math.max(0, Math.min(1, v)) * 100)}%`;
