import { useEffect, useState } from "react";
import { useReducedMotion } from "framer-motion";
import "./investigator.css";

export interface VerifiedCounterProps {
  /** Total claims the agents made. */
  claims: number;
  /** Claims the verifier confirmed against a cited, hashed source line. */
  verified: number;

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

/** Memo classification stamp and source-verification counts. */
export function VerifiedCounter({claims, verified}: VerifiedCounterProps) {
  const reduce = useReducedMotion() ?? false;
  const shownClaims = useCountUp(claims, reduce);
  const shownVerified = useCountUp(verified, reduce);
  return <div className="inv-counter">
    <div className="inv-stamp inv-stamp-secret" aria-label="Top secret">
      <span className="inv-stamp-big">TOP</span>
      <span className="inv-stamp-small">SECRET</span>
    </div>
    <p className="inv-counter-line"><span className="inv-num">{shownClaims}</span> claims made, <span className="inv-num">{shownVerified}</span> verified.</p>
  </div>;
}
