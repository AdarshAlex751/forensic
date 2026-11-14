import { useCallback, useEffect, useRef, useState } from "react";
import type { EvidenceRequest, Findings } from "../../shared/types";

const FINDINGS_URL = "/api/case/1010F/findings";
const REQUESTS_URL = "/api/investigator/requests";

/**
 * Fresh findings, fetched directly (no module cache). Nothing is fetched until
 * `refresh()` is called; the memo uses the cached `useFindings()` for first paint.
 */
export function useLiveFindings() {
  const [data, setData] = useState<Findings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const r = await fetch(FINDINGS_URL, { cache: "no-store" });
      if (!r.ok) throw new Error(`The findings request failed with status ${r.status}.`);
      const f = (await r.json()) as Findings;
      if (alive.current) {
        setData(f);
        setError(null);
      }
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (alive.current) setRefreshing(false);
    }
  }, []);

  return { data, error, refreshing, refresh };
}

/**
 * Current request statuses from the investigator's in-memory overlay. Returns
 * null when the endpoint is unavailable so callers can fall back to findings.requests.
 */
export function useRequestStatus() {
  const [requests, setRequests] = useState<EvidenceRequest[] | null>(null);
  const [available, setAvailable] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch(REQUESTS_URL, { cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      const list = (await r.json()) as unknown;
      if (Array.isArray(list)) {
        setRequests(list as EvidenceRequest[]);
        setAvailable(true);
      }
    } catch {
      setAvailable(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { requests, available, refresh, setRequests };
}

/** POST an approval; resolves with the server's reply or throws a plain-language error. */
export async function approveRequest(
  id: string,
): Promise<{ request_id: string; status: "approved"; rerun: "started" | "already running" }> {
  let r: Response;
  try {
    r = await fetch(`/api/investigator/requests/${encodeURIComponent(id)}/approve`, { method: "POST" });
  } catch {
    throw new Error("Couldn't reach the backend to approve. Start it on :8000 and try again.");
  }
  if (!r.ok) {
    throw new Error(`The backend refused the approval (status ${r.status}). Check the backend log and try again.`);
  }
  return r.json() as Promise<{ request_id: string; status: "approved"; rerun: "started" | "already running" }>;
}
