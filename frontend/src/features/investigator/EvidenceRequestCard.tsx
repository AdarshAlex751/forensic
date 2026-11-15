import { useRef } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import type { EvidenceRequest } from "../../shared/types";
import "./investigator.css";

export interface EvidenceRequestCardProps {
  request: EvidenceRequest;
  /** Called with the request id and the chosen file when the investigator uploads the requested evidence. */
  onUpload: (id: string, file: File) => void;
  /** True while the upload POST is in flight. */
  busy?: boolean;
  /** True while the pipeline reruns on the uploaded file (shows the hourglass). */
  rerunning?: boolean;
  /** Plain-language error from the last upload attempt, if any. */
  error?: string | null;
}

const STATUS_TEXT: Record<EvidenceRequest["status"], string> = {
  pending: "Waiting for the file.",
  approved: "File received, evidence being added.",
  ingested: "Added to the evidence locker.",
};

/** Small hourglass that turns while the pipeline reruns on the new evidence. */
function Hourglass({ reduce }: { reduce: boolean }) {
  return (
    <div className="inv-hourglass-row" role="status" aria-live="polite">
      <motion.svg
        className="inv-hourglass"
        viewBox="0 0 24 24"
        width="22"
        height="22"
        aria-hidden="true"
        animate={reduce ? undefined : { rotate: [0, 0, 180, 180] }}
        transition={reduce ? undefined : { duration: 2.4, times: [0, 0.4, 0.5, 1], repeat: Infinity, ease: "easeInOut" }}
      >
        <path d="M6 3h12M6 21h12M7 3c0 5 5 6 5 9s-5 4-5 9M17 3c0 5-5 6-5 9s5 4 5 9" fill="none" stroke="currentColor"
          strokeWidth="1.8" strokeLinecap="round" />
        <path d="M9.5 18.5h5L12 15.5z" fill="currentColor" />
      </motion.svg>
      <span>Re-running the analysis on the new file…</span>
    </div>
  );
}

/** An index card asking for one more piece of evidence, with an Upload file action. */
export function EvidenceRequestCard({ request, onUpload, busy, rerunning, error }: EvidenceRequestCardProps) {
  const reduce = useReducedMotion() ?? false;
  const stamped = request.status !== "pending";
  const input = useRef<HTMLInputElement>(null);

  return (
    <article className={stamped ? "inv-card inv-has-stamp" : "inv-card"} aria-label={`Evidence request: ${request.ask}`}>
      <AnimatePresence>
        {stamped && (
          <motion.span
            key="stamp"
            className="inv-approved-stamp"
            aria-hidden="true"
            initial={reduce ? { opacity: 1, rotate: -8 } : { opacity: 0, scale: 1.8, rotate: -16 }}
            animate={{ opacity: 0.9, scale: 1, rotate: -8 }}
            transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 22 }}
          >
            {request.status === "ingested" ? "Filed" : "Received"}
          </motion.span>
        )}
      </AnimatePresence>

      <p className="inv-card-ask">{request.ask}</p>
      <p className="inv-card-why">
        <span className="inv-muted">Why: </span>
        {request.why}
      </p>

      <div className="inv-card-foot">
        <span className="inv-card-status" role="status">
          {busy ? "Uploading the file…" : STATUS_TEXT[request.status]}
        </span>
        {request.status === "pending" && (
          <>
            <input
              ref={input}
              type="file"
              accept=".csv,text/csv"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = ""; // the same file can be picked again after an error
                if (f) onUpload(request.id, f);
              }}
            />
            <button type="button" className="inv-btn inv-btn-red" onClick={() => input.current?.click()} disabled={busy}>
              {busy ? "Uploading…" : "Upload file"}
            </button>
          </>
        )}
        {request.status === "approved" && !rerunning && (
          <button type="button" className="inv-btn" disabled>
            File received
          </button>
        )}
      </div>
      {rerunning && <Hourglass reduce={reduce} />}
      {error && (
        <p className="inv-state inv-state-error" role="alert" style={{ marginTop: "0.75rem" }}>
          {error}
        </p>
      )}
    </article>
  );
}
