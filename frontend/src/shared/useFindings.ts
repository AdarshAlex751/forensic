import { useEffect, useState } from "react";
import type { Findings } from "./types";

let cache: Promise<Findings> | null = null;

function load(): Promise<Findings> {
  cache ??= fetch("/api/case/1010F/findings").then((r) => {
    if (!r.ok) throw new Error(`findings request failed: ${r.status}`);
    return r.json() as Promise<Findings>;
  });
  return cache;
}

/** Forget the cached findings so the next useFindings() mount fetches again (e.g. after uploading a new case). */
export function refreshFindings(): void {
  cache = null;
}

export function useFindings() {
  const [data, setData] = useState<Findings | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    load().then(setData).catch((e: Error) => {
      cache = null; // allow retry on the next mount
      setError(e.message);
    });
  }, []);
  return { data, error, loading: !data && !error };
}
