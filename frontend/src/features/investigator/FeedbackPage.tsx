import { InvestigatorMemo } from "./InvestigatorMemo";
import "./investigator.css";

/**
 * The investigator's own page (feedback and suggestions): the memo, with its evidence requests, ranked hypotheses
 * and agent trace, on a page of its own now that the yarn board is gone. Register it as { path: "/feedback" }.
 */
export function FeedbackPage() {
  return (
    <section className="inv-page" aria-label="Investigator feedback">
      <InvestigatorMemo />
    </section>
  );
}
