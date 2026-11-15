import { useEffect, useMemo, useState } from "react";
import { useStore } from "../../shared/store";
import { useFindings } from "../../shared/useFindings";
import type { ChainStep, Contradiction, ContradictionSide } from "../../shared/types";
import { PaperShell } from "../opening/PaperShell";
import { KIND_LABEL, pct, score, seconds, stamp } from "./shared";
import "./casepages.css";

const SHOWN_PER_SIDE = 5;

interface Analysis {
  contradictions: Contradiction[];
  latest: string | null;
}

/** GET /api/analysis/contradictions: the cards plus `latest`, the finding to open on after a rerun. */
function useAnalysis(): Analysis | null {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  useEffect(() => {
    const abort = new AbortController();
    fetch("/api/analysis/contradictions", { signal: abort.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((j: { contradictions?: Contradiction[]; latest?: string | null }) => {
        setAnalysis({ contradictions: j.contradictions ?? [], latest: j.latest ?? null });
      })
      .catch(() => {
        /* the page falls back to the findings below */
      });
    return () => abort.abort();
  }, []);
  return analysis;
}

function Side({ side, chain }: { side: ContradictionSide; chain: Map<string, ChainStep> }) {
  const shown = side.events.slice(0, SHOWN_PER_SIDE);
  // `events` lists every cited event; `quotes` (and `more`) only cover the first few, so events not shown = the rest.
  const hidden = side.events.length > 0 ? side.events.length - shown.length : side.more || 0;
  const textOnly = side.quotes.slice(side.events.length); // statements about records that do not exist (no event to cite)
  return (
    <section className="cp-side" aria-label={side.label}>
      <h4>{side.label}</h4>
      {shown.map((id, i) => {
        const src = chain.get(id)?.source;
        return (
          <figure key={id} className="cp-quote">
            <blockquote>{side.quotes[i] ?? src?.quote}</blockquote>
            <figcaption>
              {src ? (
                <>
                  <span>{src.file}:{src.line}</span>
                  <span title={src.sha256}>sha256 {src.sha256.slice(0, 12)}…</span>
                </>
              ) : (
                <span>{id}</span>
              )}
            </figcaption>
          </figure>
        );
      })}
      {textOnly.map((q, i) => (
        <figure key={`t${i}`} className="cp-quote cp-quote--plain">
          <blockquote>{q}</blockquote>
        </figure>
      ))}
      {hidden > 0 && <p className="cp-more">+{hidden} more record{hidden === 1 ? "" : "s"} cited</p>}
    </section>
  );
}

/**
 * /contradictions: what conflicts. The list on the left is every contradiction; the card on the right shows the
 * selected one with both sides side by side. It opens on `latest` (the finding new or updated by the last rerun, e.g.
 * after released evidence) when there is one, otherwise on the first. Nothing here is invented: every label, quote,
 * file, line, hash, score, walk time and gap comes from the data.
 */
export function ContradictionsPage() {
  const { data, error } = useFindings();
  const analysis = useAnalysis();
  const selectedId = useStore((s) => s.selectedContradictionId);
  const select = useStore((s) => s.setSelectedContradictionId);

  const list = analysis?.contradictions ?? data?.contradictions ?? [];
  const current: Contradiction | undefined =
    list.find((c) => c.id === selectedId) ?? list.find((c) => c.id === analysis?.latest) ?? list[0];

  const chain = useMemo(() => new Map((current?.chain ?? []).map((s) => [s.event, s])), [current]);
  const hypotheses = (data?.hypotheses ?? []).filter((h) => current && h.supports.includes(current.id));

  return (
    <PaperShell label="Contradictions">
      <div className="casepage">
        <header className="cp-head">
          <h1>Contradictions</h1>
          <p>Where the records disagree with each other or with what was said. Each side cites the original file and line.</p>
        </header>

        {error && list.length === 0 ? (
          <p className="cp-state cp-state--error" role="alert">Couldn’t load the case data. Start the backend on port 8000 and reload this page.</p>
        ) : list.length === 0 ? (
          <p className="cp-state" role="status">{data || analysis ? "No contradictions in this case." : "Loading the case data…"}</p>
        ) : (
          <div className="cp-cols cp-cols--contradictions">
            <section className="cp-panel cp-list" aria-label="All contradictions">
              <ol>
                {list.map((c, i) => (
                  <li key={c.id} style={{ ["--i" as string]: Math.min(i, 12) }}>
                    <button type="button" className="cp-row cp-row--c" aria-pressed={c.id === current?.id} onClick={() => select(c.id)}>
                      <span className="cp-cid">{c.id}</span>
                      <span className="cp-who">
                        <strong>{c.title ?? c.explanation}</strong>
                        <small>
                          <span className="cp-chip">{KIND_LABEL[c.kind] ?? c.kind}</span>
                          {c.change && <span className="cp-chip cp-chip--ink">{c.change}</span>}
                        </small>
                      </span>
                      <span className="cp-score">{score(c.score)}</span>
                      <span className="cp-bar" aria-hidden="true"><i style={{ width: pct(c.score) }} /></span>
                    </button>
                  </li>
                ))}
              </ol>
            </section>

            {current && (
              <article className="cp-panel cp-card" aria-label={`${current.id}, details`}>
                <span className="cp-tape" aria-hidden="true" />
                <div className="cp-card-head">
                  <div>
                    <h2>{current.title ?? current.id}</h2>
                    <p className="cp-sub">
                      <span className="cp-chip">{KIND_LABEL[current.kind] ?? current.kind}</span>
                      <span className="cp-chip cp-chip--ink">{current.id}</span>
                      {current.change && <span className="cp-chip cp-chip--ink">{current.change}</span>}
                      {current.t && <span className="cp-when">{stamp(current.t)}</span>}
                    </p>
                  </div>
                  <div className="cp-big" aria-label={`Score ${score(current.score)}`}>
                    <b>{score(current.score)}</b>
                    <small>score</small>
                    <span className="cp-bar" aria-hidden="true"><i style={{ width: pct(current.score) }} /></span>
                  </div>
                </div>

                <p className="cp-explain">{current.explanation}</p>

                <dl className="cp-facts">
                  {current.walk_s != null && current.gap_s != null && (
                    <div>
                      <dt>{current.path?.length ? `Route ${current.path.join(" → ")}` : "Walk time"}</dt>
                      <dd>
                        walk {seconds(current.walk_s)} against a gap of {seconds(current.gap_s)}
                        {current.rule === "impossible_travel" && <span className="cp-stamp">IMPOSSIBLE</span>}
                      </dd>
                    </div>
                  )}
                  {current.walk_s == null && current.gap_s != null && (
                    <div><dt>Gap</dt><dd>{seconds(current.gap_s)}</dd></div>
                  )}
                  {current.rule === "nli" && (
                    <div><dt>NLI score</dt><dd>{score(current.score)} (statement against the records)</dd></div>
                  )}
                  {hypotheses.map((h) => (
                    <div key={h.id}>
                      <dt>Investigator confidence</dt>
                      <dd>{score(h.confidence)} <span className="cp-faint">({h.id})</span></dd>
                    </div>
                  ))}
                </dl>

                <div className="cp-sides">
                  {(current.sides ?? []).map((s) => (
                    <Side key={s.label} side={s} chain={chain} />
                  ))}
                </div>


              </article>
            )}
          </div>
        )}
      </div>
    </PaperShell>
  );
}
