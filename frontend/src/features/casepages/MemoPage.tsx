import { InvestigatorMemo } from "../investigator/InvestigatorMemo";
import { PaperShell } from "../opening/PaperShell";
import "./casepages.css";

/** /memo: the investigator memo (ranked hypotheses, evidence requests, agent trace) in the shared paper frame. */
export function MemoPage() {
  return (
    <PaperShell label="Investigator memo">
      <div className="casepage cp-memo">
        <InvestigatorMemo />
      </div>
    </PaperShell>
  );
}
