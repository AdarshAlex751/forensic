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
import { approveRequest, useLiveFindings, useRequestStatus } from "./useLiveFindings";
import { usePipelineProgress } from "./usePipelineProgress";
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

/**
 * The investigator's typed memo, clipped over the yarn board. Reads findings,
 * current request statuses, the pipeline progress stream and the agent stream.
 */
export function InvestigatorMemo() {
  const initial = useFindings();
  const live = useLiveFindings();
  const reqs = useRequestStatus();
  const trace = useAgentTrace();

  const [showReport, setShowReport] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [approveErrors, setApproveErrors] = useState<Record<string, string>>({});
  const [localStatus, setLocalStatus] = useState<Record<string, EvidenceRequest["status"]>>({});
  const [prevConf, setPrevConf] = useState<Record<string, number>>({});

  const findings: Findings | null = live.data ?? initial.data;
  const findingsRef = useRef(findings);
  findingsRef.current = findings;

  const onRunFinished = useCallback(() => {
    const current = findingsRef.current;
    if (current) setPrevConf(Object.fromEntries(current.hypotheses.map((h) => [h.id, h.confidence])));
    void live.refresh();
    void reqs.refresh().then(() => setLocalStatus({}));
  }, [live.refresh, reqs.refresh]);

  const pipeline = usePipelineProgress(onRunFinished);

  const onApprove = useCallback(
    async (id: string) => {
      setBusyId(id);
      setApproveErrors(({ [id]: _drop, ...rest }) => rest);
      try {
        await approveRequest(id);
        setLocalStatus((s) => ({ ...s, [id]: "approved" }));
        trace.reconnect();
        pipeline.watch();
      } catch (e) {
        setApproveErrors((m) => ({ ...m, [id]: e instanceof Error ? e.message : String(e) }));
      } finally {
        setBusyId(null);
      }
    },
    [trace.reconnect, pipeline.watch],
  );

  const requests = useMemo<EvidenceRequest[]>(() => {
    const base = reqs.requests ?? findings?.requests ?? [];
    return base.map((r) => {
      const local = localStatus[r.id];
      // Never move a request backwards (e.g. a stale "pending" after we saw "approved").
      if (local && r.status === "pending") return { ...r, status: local };
      return r;
    });
  }, [reqs.requests, findings?.requests, localStatus]);

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
  const running = pipeline.state === "watching";

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
            <dd>{findings.case.id}</dd>
          </dl>
        </div>
        <button type="button" className="inv-btn" onClick={() => setShowReport(true)} aria-haspopup="dialog">
          Open case report
        </button>
      </header>

      <section className="inv-section" aria-label="Verification">
        <VerifiedCounter claims={v.claims} verified={v.verified} />
        {live.error && (
          <p className="inv-state inv-state-error" role="alert" style={{ marginTop: "0.75rem" }}>
            <strong>Couldn't reload the findings after the re-run.</strong>
            Showing the previous version. Check that the backend on :8000 is running. ({live.error})
          </p>
        )}
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
                previousConfidence={prevConf[h.id]}
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
        {!reqs.available && requests.length > 0 && (
          <p className="inv-muted inv-plain" style={{ marginBottom: "0.6rem", fontSize: "0.8125rem" }}>
            Live request status is unavailable, so these statuses come from the last saved findings.
          </p>
        )}
        {requests.length === 0 ? (
          <p className="inv-state">The investigator has not asked for more evidence.</p>
        ) : (
          <div className="inv-cards">
            {requests.map((r) => (
              <EvidenceRequestCard
                key={r.id}
                request={r}
                onApprove={(id) => void onApprove(id)}
                busy={busyId === r.id}
                error={approveErrors[r.id] ?? null}
              />
            ))}
          </div>
        )}
        {pipeline.state !== "idle" && (
          <div className="inv-progress" role="status">
            {running ? (
              <>
                Re-running the pipeline
                {pipeline.progress?.stage ? `: ${pipeline.progress.stage}` : ""}
                {pipeline.progress?.msg ? `. ${pipeline.progress.msg}` : "."}
                <div className="inv-progress-track" aria-hidden="true">
                  <div className="inv-progress-fill" style={{ width: `${pipeline.progress?.pct ?? 0}%` }} />
                </div>
              </>
            ) : live.refreshing ? (
              "Pipeline finished. Reloading the findings…"
            ) : pipeline.state === "lost" ? (
              "Couldn't follow the pipeline progress, so the findings were reloaded once. Reload the page if they look out of date."
            ) : (
              "Pipeline finished. The findings above are up to date."
            )}
          </div>
        )}
      </section>

      <section className="inv-section" aria-labelledby="inv-h-trace">
        <h3 id="inv-h-trace" className="inv-section-title">
          Agent activity
        </h3>
        <AgentTrace events={trace.events} todos={trace.todos} status={trace.status} />
      </section>

      {showReport && <ReportDialog findings={findings} onClose={closeReport} />}
    </aside>
  );
}
