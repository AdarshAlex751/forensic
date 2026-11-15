import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useStore } from "../../shared/store";
import { useFindings } from "../../shared/useFindings";
import type { Person } from "../../shared/types";
import { PaperShell } from "../opening/PaperShell";
import { KIND_LABEL, pct, score } from "./shared";
import "./casepages.css";

/**
 * /red-flags: who looks unusual. People ranked by anomaly score, each with the measures behind it (from
 * persons[].red_flags) and any context the data gives that explains part of it (persons[].context). A score means
 * "unusual day against their own usual day", never a verdict. Every word and number comes from findings.
 */
export function RedFlagsPage() {
  const { data, error } = useFindings();
  const navigate = useNavigate();
  const selectedId = useStore((s) => s.selectedPersonId);
  const selectPerson = useStore((s) => s.setSelectedPersonId);
  const selectContradiction = useStore((s) => s.setSelectedContradictionId);

  const ranked = useMemo<Person[]>(
    () => (data?.persons ?? []).filter((p) => p.anomaly > 0).sort((a, b) => b.anomaly - a.anomaly),
    [data],
  );
  const current = ranked.find((p) => p.id === selectedId) ?? ranked[0];
  const involved = useMemo(
    () => (current ? (data?.contradictions ?? []).filter((c) => c.persons?.includes(current.id)) : []),
    [data, current],
  );

  return (
    <PaperShell label="Red flags">
      <div className="casepage">
        <header className="cp-head">
          <h1>Red flags</h1>
          <p>People ranked by how unusual their day was against their own usual day. A score means “unusual”, never a verdict.</p>
        </header>

        {error ? (
          <p className="cp-state cp-state--error" role="alert">Couldn’t load the case data. Start the backend on port 8000 and reload this page.</p>
        ) : !data ? (
          <p className="cp-state" role="status">Loading the case data…</p>
        ) : ranked.length === 0 ? (
          <p className="cp-state" role="status">No one has an anomaly score in this case.</p>
        ) : (
          <div className="cp-cols cp-cols--people">
            <section className="cp-panel cp-list" aria-label="People ranked by anomaly score">
              <ol>
                {ranked.map((p, i) => {
                  const explained = (p.context?.length ?? 0) > 0;
                  return (
                    <li key={p.id} style={{ ["--i" as string]: Math.min(i, 12) }}>
                      <button type="button" className="cp-row" aria-pressed={p.id === current?.id} onClick={() => selectPerson(p.id)}>
                        <span className="cp-rank">{p.anomaly_rank ?? i + 1}</span>
                        <span className="cp-who">
                          <strong>{p.name}</strong>
                          <small>{p.role}</small>
                        </span>
                        {explained && <span className="cp-chip cp-chip--ink">Explained</span>}
                        <span className="cp-score">{score(p.anomaly)}</span>
                        <span className="cp-bar" aria-hidden="true"><i style={{ width: pct(p.anomaly) }} /></span>
                      </button>
                    </li>
                  );
                })}
              </ol>
            </section>

            {current && (
              <article className="cp-panel cp-card" aria-label={`${current.name}, details`}>
                <span className="cp-tape" aria-hidden="true" />
                <div className="cp-card-head">
                  <div>
                    <h2>{current.name}</h2>
                    <p className="cp-sub">{current.role}{current.suite ? `, suite ${current.suite}` : ""}</p>
                  </div>
                  <div className="cp-big" aria-label={`Anomaly score ${score(current.anomaly)}`}>
                    <b>{score(current.anomaly)}</b>
                    <small>anomaly{current.anomaly_rank ? `, rank ${current.anomaly_rank}` : ""}</small>
                  </div>
                </div>

                {(current.context ?? []).map((c, i) => (
                  <p key={i} className="cp-note cp-note--explained">
                    <span className="cp-chip cp-chip--ink">Explained</span> {c.text}
                  </p>
                ))}

                <h3>Behind the score</h3>
                {(current.red_flags ?? []).length === 0 ? (
                  <p className="cp-empty">No measure is above this person’s own usual day.</p>
                ) : (
                  <ul className="cp-flags">
                    {(current.red_flags ?? []).map((f) => (
                      <li key={f.feature}>
                        <span className="cp-flag-label">{f.label}</span>
                        <span className="cp-flag-text">{f.text}</span>
                      </li>
                    ))}
                  </ul>
                )}

                <h3>Contradictions that involve them</h3>
                {involved.length === 0 ? (
                  <p className="cp-empty">No contradiction cites this person.</p>
                ) : (
                  <ul className="cp-links">
                    {involved.map((c) => (
                      <li key={c.id}>
                        <button
                          type="button"
                          className="cp-link"
                          onClick={() => {
                            selectContradiction(c.id);
                            navigate("/contradictions");
                          }}
                        >
                          <span className="cp-chip">{KIND_LABEL[c.kind] ?? c.kind}</span>
                          <span className="cp-link-title">{c.title ?? c.explanation}</span>
                          <span className="cp-link-id">{c.id}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </article>
            )}
          </div>
        )}
      </div>
    </PaperShell>
  );
}
