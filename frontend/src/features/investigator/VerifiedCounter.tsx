import { useEffect, useState } from "react";
import { useReducedMotion } from "framer-motion";
import "./investigator.css";

export interface VerifiedCounterProps {
  /** Total claims the agents made. */
  claims: number;
  /** Claims the verifier confirmed against a cited, hashed source line. */
  verified: number;
  /** Claims the verifier threw out. */
  rejectedCount: number;
  /** Opens the rejected-claims list. When omitted the number is plain text. */
  onShowRejected?: () => void;
  /** Whether the rejected list is currently open (for aria-expanded). */
  rejectedOpen?: boolean;
  /** id of the element the button controls. */
  rejectedListId?: string;
}

/** Counts from 0 to `target` over ~450ms; returns the target immediately under reduced motion. */
function useCountUp(target: number, reduce: boolean): number {
  const [value, setValue] = useState(reduce ? target : 0);
  useEffect(() => {
    if (reduce) {
      setValue(target);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const duration = 450;
    const tick = (now: number) => {
      const k = Math.min(1, (now - start) / duration);
      setValue(Math.round(target * (1 - (1 - k) ** 3)));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, reduce]);
  return value;
}

/** "N claims made, M verified, K rejected" with a rubber-stamp verified percentage. */
export function VerifiedCounter({
  claims,
  verified,
  rejectedCount,
  onShowRejected,
  rejectedOpen,
  rejectedListId,
}: VerifiedCounterProps) {
  const reduce = useReducedMotion() ?? false;
  const shownClaims = useCountUp(claims, reduce);
  const shownVerified = useCountUp(verified, reduce);
  const percent = claims > 0 ? Math.round((verified / claims) * 100) : null;

  return (
    <div className="inv-counter">
      <div className="inv-stamp" aria-hidden="true">
        <span className="inv-stamp-big">{percent === null ? "n/a" : `${percent}%`}</span>
        <span className="inv-stamp-small">verified</span>
      </div>
      <p className="inv-counter-line">
        <span className="inv-num">{shownClaims}</span> claims made,{" "}
        <span className="inv-num">{shownVerified}</span> verified,{" "}
        {onShowRejected && rejectedCount > 0 ? (
          <button
            type="button"
            className="inv-linkbtn inv-num"
            onClick={onShowRejected}
            aria-expanded={rejectedOpen}
            aria-controls={rejectedListId}
            aria-label={`${rejectedCount} rejected. ${rejectedOpen ? "Hide" : "Show"} rejected claims`}
          >
            {rejectedCount}
          </button>
        ) : (
          <span className="inv-num">{rejectedCount}</span>
        )}{" "}
        rejected.
        {percent !== null && <span className="inv-sr-only"> {percent} percent verified.</span>}
      </p>
    </div>
  );
}
