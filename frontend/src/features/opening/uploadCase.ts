// Uploads a case zip to POST /api/evidence/upload. XMLHttpRequest (not fetch) because only it reports upload progress.

export interface UploadResult {
  case_id: string;
  filename: string;
  files: number;
}

export const ZIP_MESSAGE = "Upload a .zip containing one case folder";
const NETWORK_MESSAGE = "Couldn’t reach the backend. Start it on port 8000 and try again.";
const TIMEOUT_MS = 5 * 60 * 1000;

export const isZip = (f: File) => f.name.toLowerCase().endsWith(".zip");

/** The server explains itself in `detail` (a string for 400s, a list of {msg} for 422s). */
export function errorText(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (Array.isArray(detail)) {
    const msgs = detail.map((d) => (d && typeof d === "object" ? (d as { msg?: unknown }).msg : null)).filter((m): m is string => typeof m === "string");
    if (msgs.length) return msgs.join("; ");
  }
  return status >= 500
    ? `The backend failed while reading the file (status ${status}). Check the backend log and try again.`
    : `The backend refused the file (status ${status}). Try again.`;
}

export interface Upload {
  done: Promise<UploadResult>;
  abort: () => void;
}

/** onProgress gets 0..100 while the bytes go up. Rejects with an Error whose message is safe to show. */
export function uploadCase(file: File, onProgress: (pct: number) => void): Upload {
  const xhr = new XMLHttpRequest();
  const done = new Promise<UploadResult>((resolve, reject) => {
    xhr.open("POST", "/api/evidence/upload");
    xhr.responseType = "text";
    xhr.timeout = TIMEOUT_MS;
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && e.total > 0) onProgress(Math.min(100, Math.round((e.loaded / e.total) * 100)));
    };
    xhr.onerror = () => reject(new Error(NETWORK_MESSAGE));
    xhr.ontimeout = () => reject(new Error("The upload took too long. Check your connection and try again."));
    xhr.onabort = () => reject(new Error("Upload cancelled."));
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* not JSON: errorText falls back to the status */
      }
      if (xhr.status < 200 || xhr.status >= 300) return reject(new Error(errorText(xhr.status, body)));
      const r = body as Partial<UploadResult> | null;
      if (!r || typeof r.case_id !== "string" || typeof r.filename !== "string") {
        return reject(new Error("The backend accepted the file but sent an unexpected reply. Try again."));
      }
      resolve({ case_id: r.case_id, filename: r.filename, files: typeof r.files === "number" ? r.files : 0 });
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
  return { done, abort: () => xhr.abort() };
}
