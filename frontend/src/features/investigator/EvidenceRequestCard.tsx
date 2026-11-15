import { motion, useReducedMotion } from "framer-motion";
import type { EvidenceRequest } from "../../shared/types";
import "./investigator.css";

export interface EvidenceRequestCardProps {
  request: EvidenceRequest;
}

/**
 * An index card for one evidence request. The card is always shown filed: the request, why it was asked, the red FILED
 * stamp, and "Added to the evidence locker." It is static on purpose (the upload step is explained, not run): there are
 * no buttons, inputs or file pickers here, and nothing on it sends anything to the backend.
 */
export function EvidenceRequestCard({ request }: EvidenceRequestCardProps) {
  const reduce = useReducedMotion() ?? false;

  return (
    <article className="inv-card inv-has-stamp" aria-label={`Evidence request: ${request.ask}`}>
      <motion.span
        className="inv-approved-stamp"
        aria-hidden="true"
        initial={reduce ? { opacity: 1, rotate: -8 } : { opacity: 0, scale: 1.8, rotate: -16 }}
        animate={{ opacity: 0.9, scale: 1, rotate: -8 }}
        transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 520, damping: 22 }}
      >
        Filed
      </motion.span>

      <p className="inv-card-ask">{request.ask}</p>
      <p className="inv-card-why">
        <span className="inv-muted">Why: </span>
        {request.why}
      </p>

      <div className="inv-card-foot">
        <span className="inv-card-status">Added to the evidence locker.</span>
      </div>
    </article>
  );
}
