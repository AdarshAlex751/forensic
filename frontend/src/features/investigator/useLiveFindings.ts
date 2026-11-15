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

export type ApproveReply = {
  request_id: string;
  status: "approved";
  released: string[];
  rerun: "started" | "already running";
};

export type UploadReply = Omit<ApproveReply, "rerun"> & { file?: string; rerun: "started" | "queued" };

/** Upload the requested evidence file for a request; the backend adds it to the case and reruns the pipeline. */
export async function uploadRequestFile(id: string, file: File): Promise<UploadReply> {
  const body = new FormData();
  body.append("file", file);
  let r: Response;
  try {
    r = await fetch(`/api/investigator/requests/${encodeURIComponent(id)}/upload`, { method: "POST", body });
  } catch {
    throw new Error("Couldn't reach the backend to upload the file. Start it on :8000 and try again.");
  }
  if (!r.ok) {
    let detail = "";
    try {
      const j = (await r.json()) as { detail?: unknown };
      if (typeof j.detail === "string") detail = j.detail;
    } catch {
      /* not JSON */
    }
    throw new Error(
      detail
        ? `${detail} The request is still open; upload the right file to continue.`
        : `The backend refused the upload (status ${r.status}). Check the backend log and try again.`,
    );
  }
  return r.json() as Promise<UploadReply>;
}

/** POST an approval; resolves with the server's reply or throws a plain-language error. */
export async function approveRequest(
  id: string,
): Promise<ApproveReply> {
  let r: Response;
  try {
    r = await fetch(`/api/investigator/requests/${encodeURIComponent(id)}/approve`, { method: "POST" });
  } catch {
    throw new Error("Couldn't reach the backend to approve. Start it on :8000 and try again.");
  }
  if (!r.ok) {
    // The backend explains itself in `detail` (e.g. the evidence could not be released); the request stays pending.
    let detail = "";
    try {
      const body = (await r.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* not JSON: fall back to the generic text */
    }
    throw new Error(
      detail
        ? `${detail} The request is still pending. Try again once the evidence is available.`
        : `The backend refused the approval (status ${r.status}). Check the backend log and try again.`,
    );
  }
  return r.json() as Promise<ApproveReply>;
}
