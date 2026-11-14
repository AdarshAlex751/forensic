import type { EventRec, Person, Source } from "../../shared/types";

/**
 * Splits an ISO timestamp into the date and clock time exactly as written.
 * Times in this case carry a fixed -05:00 offset; we never convert to the
 * browser's timezone, we only read the characters.
 */
export function splitIso(iso: string): { date: string; time: string; offset: string } {
  const m = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?/.exec(iso);
  if (!m) return { date: "", time: iso, offset: "" };
  return { date: m[1], time: m[2], offset: m[3] ?? "" };
}

/** "2026-02-24 13:00:00 (-05:00)" style, read straight from the string. */
export function formatTimeAsWritten(iso: string): string {
  const { date, time, offset } = splitIso(iso);
  if (!date) return time;
  return `${date} ${time}${offset ? ` (${offset === "-05:00" ? "EST" : offset})` : ""}`;
}

/** First 8 hex characters of a sha256, the length used in citations. */
export function shortSha(sha: string | undefined | null): string {
  return (sha ?? "").slice(0, 8) || "no-hash";
}

/** "it/maintenance_calendar.csv:2" */
export function cite(source: Pick<Source, "file" | "line">): string {
  return `${source.file}:${source.line}`;
}

/** Whole percentage for a 0..1 value, clamped. */
export function pct(v: number): number {
  if (!Number.isFinite(v)) return 0;
  return Math.round(Math.min(1, Math.max(0, v)) * 100);
}

/** An event's optional raw actor, present in some evidence rows but not in the shared type. */
interface RawActor {
  kind?: string;
  value?: string;
}

function readActor(e: EventRec): RawActor | string | null {
  const actor = (e as EventRec & { actor?: unknown }).actor;
  if (typeof actor === "string") return actor;
  if (actor && typeof actor === "object") return actor as RawActor;
  return null;
}

/**
 * Who an event is about: the resolved person's name when known, otherwise the
 * raw actor as it appears in the evidence, otherwise null.
 */
export function eventActorLabel(e: EventRec, persons: ReadonlyMap<string, Person>): string | null {
  if (e.person) {
    const p = persons.get(e.person);
    return p ? p.name : e.person;
  }
  const actor = readActor(e);
  if (typeof actor === "string") return `unresolved: ${actor}`;
  if (actor && (actor.value || actor.kind)) {
    return `unresolved ${actor.kind ?? "actor"}: ${actor.value ?? "unknown"}`;
  }
  return null;
}

/** Turns a snake_case event type into readable words. */
export function humanize(s: string): string {
  return s.replace(/[_-]+/g, " ").trim();
}
