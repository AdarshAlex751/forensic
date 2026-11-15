import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { EvidenceRequest, Findings, Note } from "../../shared/types";
import { useFindings } from "../../shared/useFindings";
import { AgentTrace } from "./AgentTrace";
import { CaseReport } from "./CaseReport";
import { EvidenceRequestCard } from "./EvidenceRequestCard";
import { HypothesisBar } from "./HypothesisBar";
import { VerifiedCounter } from "./VerifiedCounter";
import { useAgentTrace } from "./useAgentTrace";
import { genericTodos, genericTrace, withGenericNames } from "./generic";
import "./investigator.css";

const NOTE_GROUPS: { kind: Note["kind"]; title: string; className: string }[] = [
  { kind: "check_next", title: "What to check next", className: "inv-notes-check" },
  { kind: "todo", title: "To do", className: "" },
  { kind: "cleared", title: "Cleared", className: "inv-notes-cleared" },
];

/** Full-screen report sheet rendered at the body root so print CSS can isolate it. */
function ReportDialog({ findings, onClose }: { findings: Findings; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      opener?.focus?.();
    };
  }, [onClose]);

  return createPortal(
    <div className="inv-print-root">
      <div className="inv-report-overlay" role="dialog" aria-modal="true" aria-labelledby="inv-report-title">
        <CaseReport findings={findings} onClose={onClose} closeRef={closeRef} />
      </div>
    </div>,
    document.body,
  );
}

/** One status rank per request state, so the furthest-along copy of a duplicated request is the one kept. */
const STATUS_RANK: Record<EvidenceRequest["status"], number> = { pending: 0, approved: 1, ingested: 2 };
const normalize = (text: string) => text.toLowerCase().replace(/\s+/g, " ").trim();

/**
 * One card per request. The same id, the same wording, or two requests that both ask for the parking log are one
 * request, shown once (the furthest-along copy wins). The cards are all rendered filed, so only this matters here.
 */
function distinctRequests(list: EvidenceRequest[]): EvidenceRequest[] {
  const seen = new Set<string>();
  return [...list]
    .sort((a, b) => STATUS_RANK[b.status] - STATUS_RANK[a.status])
    .filter((r) => {
      const keys = [`id:${r.id}`, `ask:${normalize(r.ask)}`, ...(/parking/i.test(r.ask) ? ["source:parking"] : [])];
      if (keys.some((k) => seen.has(k))) return false;
      keys.forEach((k) => seen.add(k));
      return true;
    });
}

/**
 * The investigator's typed memo. Reads the findings and the agent activity stream. It is static as far as evidence
 * goes: the requests are shown filed, and this page never uploads, approves, releases or reruns anything.
 */
export function InvestigatorMemo() {
  const initial = useFindings();
  const trace = useAgentTrace();

  const [showReport, setShowReport] = useState(false);
  const genericEvents = useMemo(() => genericTrace(trace.events), [trace.events]);
  const genericPlan = useMemo(() => genericTodos(trace.todos), [trace.todos]);

  const findings: Findings | null = useMemo(() => (initial.data ? withGenericNames(initial.data) : null), [initial.data]);
  const requests = useMemo(() => (findings ? distinctRequests(findings.requests) : []), [findings]);

  const hypotheses = useMemo(
    () => (findings ? [...findings.hypotheses].sort((a, b) => b.confidence - a.confidence) : []),
    [findings],
  );

  const closeReport = useCallback(() => setShowReport(false), []);

  if (!findings) {
    return (
      <aside className="inv-memo" aria-label="Investigator memo" aria-busy={initial.loading}>
        <span className="inv-clip" aria-hidden="true" />
        <h2 className="inv-memo-title">Investigator memo</h2>
        {initial.error ? (
          <p className="inv-state inv-state-error" role="alert">
            <strong>Couldn't load the case data.</strong>
            Start the backend on :8000 and reload the page. ({initial.error})
          </p>
        ) : (
          <p className="inv-state" role="status">
            Loading the case findings…
          </p>
        )}
      </aside>
    );
  }

  const v = findings.verification;
  const notesByKind = (kind: Note["kind"]) => findings.notes.filter((n) => n.kind === kind);

  return (
    <aside className="inv-memo" aria-label="Investigator memo">
      <span className="inv-clip" aria-hidden="true" />

      <header className="inv-memo-head">
        <div>
          <h2 className="inv-memo-title">Investigator memo</h2>
          <dl className="inv-memo-lines">
            <dt>Re:</dt>
            <dd>{findings.case.title}</dd>
            <dt>File:</dt>
            <dd>Princeton Files</dd>
          </dl>
        </div>
        <button type="button" className="inv-btn" onClick={() => setShowReport(true)} aria-haspopup="dialog">
          Open case report
        </button>
      </header>

      <section className="inv-section" aria-label="Verification">
        <VerifiedCounter claims={v.claims} verified={v.verified} />
      </section>

      <section className="inv-section" aria-labelledby="inv-h-hyp">
        <h3 id="inv-h-hyp" className="inv-section-title">
          Hypotheses, ranked by confidence
        </h3>
        {hypotheses.length === 0 ? (
          <p className="inv-state">The investigator has not proposed any hypotheses yet.</p>
        ) : (
          <ol className="inv-hyps">
            {hypotheses.map((h, i) => (
              <HypothesisBar
                key={h.id}
                rank={i + 1}
                hypothesis={h}
                contradictions={findings.contradictions}
              />
            ))}
          </ol>
        )}
      </section>

      <section className="inv-section" aria-labelledby="inv-h-notes">
        <h3 id="inv-h-notes" className="inv-section-title">
          Notes
        </h3>
        {findings.notes.length === 0 ? (
          <p className="inv-state">No notes yet.</p>
        ) : (
          <div className="inv-notes">
            {NOTE_GROUPS.map((g) => {
              const items = notesByKind(g.kind);
              if (items.length === 0) return null;
              return (
                <div key={g.kind}>
                  <h4>{g.title}</h4>
                  <ul className={g.className || undefined}>
                    {items.map((n, i) => (
                      <li key={`${i}-${n.text}`}>{n.text}</li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="inv-section" aria-labelledby="inv-h-req">
        <h3 id="inv-h-req" className="inv-section-title">
          Evidence requests
        </h3>
        {requests.length === 0 ? (
          <p className="inv-state">The investigator has not asked for more evidence.</p>
        ) : (
          <div className="inv-cards">
            {requests.map((r) => (
              <EvidenceRequestCard key={r.id} request={r} />
            ))}
          </div>
        )}
      </section>

      <section className="inv-section" aria-labelledby="inv-h-trace">
        <h3 id="inv-h-trace" className="inv-section-title">
          Agent activity
        </h3>
        <AgentTrace events={genericEvents} todos={genericPlan} status={trace.status} />
      </section>

      {showReport && <ReportDialog findings={findings} onClose={closeReport} />}
    </aside>
  );
}
