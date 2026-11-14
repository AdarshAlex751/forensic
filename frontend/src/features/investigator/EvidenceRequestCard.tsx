import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import type { EvidenceRequest } from "../../shared/types";
import "./investigator.css";

export interface EvidenceRequestCardProps {
  request: EvidenceRequest;
  /** Called with the request id when the investigator presses Approve. */
  onApprove: (id: string) => void;
  /** True while the approval POST is in flight. */
  busy?: boolean;
  /** Plain-language error from the last approval attempt, if any. */
  error?: string | null;
}

const STATUS_TEXT: Record<EvidenceRequest["status"], string> = {
  pending: "Waiting for your approval.",
  approved: "Approved, evidence being added.",
  ingested: "Added to the evidence locker.",
};

/** An index card asking for one more piece of evidence, with an Approve action. */
export function EvidenceRequestCard({ request, onApprove, busy, error }: EvidenceRequestCardProps) {
  const reduce = useReducedMotion() ?? false;
  const stamped = request.status !== "pending";

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
            {request.status === "ingested" ? "Filed" : "Approved"}
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
          {busy ? "Sending approval…" : STATUS_TEXT[request.status]}
        </span>
        {request.status === "pending" && (
          <button
            type="button"
            className="inv-btn inv-btn-red"
            onClick={() => onApprove(request.id)}
            disabled={busy}
          >
            {busy ? "Approving…" : "Approve"}
          </button>
        )}
        {request.status === "approved" && (
          <button type="button" className="inv-btn" disabled>
            Approved, evidence being added
          </button>
        )}
      </div>
      {error && (
        <p className="inv-state inv-state-error" role="alert" style={{ marginTop: "0.75rem" }}>
          {error}
        </p>
      )}
    </article>
  );
}
