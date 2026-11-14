import { motion, useReducedMotion } from "framer-motion";
import { useId } from "react";
import type { Contradiction, Hypothesis } from "../../shared/types";
import { pct } from "./format";
import "./investigator.css";

export interface HypothesisBarProps {
  hypothesis: Hypothesis;
  /** All contradictions; used to describe the ones this hypothesis rests on. */
  contradictions?: Contradiction[];
  /** Confidence before the latest re-run, so the bar can move from there. */
  previousConfidence?: number;
  /** 1-based rank in the sorted list. */
  rank?: number;
}

/** One ranked hypothesis: animated confidence meter, its supports, and what would disprove it. */
export function HypothesisBar({ hypothesis, contradictions, previousConfidence, rank }: HypothesisBarProps) {
  const reduce = useReducedMotion() ?? false;
  const textId = useId();
  const now = pct(hypothesis.confidence);
  const before = previousConfidence === undefined ? undefined : pct(previousConfidence);
  const delta = before === undefined ? 0 : now - before;
  const byId = new Map((contradictions ?? []).map((c) => [c.id, c]));

  return (
    <li className="inv-hyp">
      <span className="inv-hyp-rank" aria-hidden="true">
        {rank ?? ""}
      </span>
      <div>
        <p id={textId} className="inv-hyp-text">
          {rank !== undefined && <span className="inv-sr-only">Rank {rank}. </span>}
          {hypothesis.text}
        </p>

        <div className="inv-meter-row">
          <div
            className="inv-meter"
            role="meter"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={now}
            aria-valuetext={`${now}% confidence`}
            aria-labelledby={textId}
          >
            <motion.div
              className="inv-meter-fill"
              initial={{ width: `${before ?? (reduce ? now : 0)}%` }}
              animate={{ width: `${now}%` }}
              transition={reduce ? { duration: 0 } : { duration: 0.8, ease: [0.2, 0.8, 0.2, 1] }}
            />
          </div>
          <span className="inv-meter-value">
            {now}%
            {delta !== 0 && (
              <span className="inv-delta">
                {delta > 0 ? "up" : "down"} {Math.abs(delta)} from {before}%
              </span>
            )}
          </span>
        </div>

        {hypothesis.supports.length > 0 ? (
          <p className="inv-supports">
            Rests on:{" "}
            {hypothesis.supports.map((id) => {
              const c = byId.get(id);
              return (
                <span key={id} className="inv-chip" title={c?.explanation}>
                  {id}
                  {c ? `, ${c.kind}, score ${c.score.toFixed(2)}` : ""}
                </span>
              );
            })}
          </p>
        ) : (
          <p className="inv-supports inv-muted">No contradiction supports this yet.</p>
        )}

        <div className="inv-disprove">
          <p className="inv-disprove-title">What would disprove this</p>
          <p>{hypothesis.disproved_by || "The agent did not state a disproving test."}</p>
        </div>
      </div>
    </li>
  );
}
