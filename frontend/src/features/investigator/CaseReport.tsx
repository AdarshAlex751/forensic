import { Fragment, useMemo, type Ref } from "react";
import type { EventRec, Findings, Person, Source } from "../../shared/types";
import { cite, eventActorLabel, formatTimeAsWritten, humanize, pct, shortSha } from "./format";
import "./investigator.css";

export interface CaseReportProps {
  findings: Findings;
  /** Optional close action shown in the toolbar. */
  onClose?: () => void;
  /** Ref target for the close button, so a dialog can focus it on open. */
  closeRef?: Ref<HTMLButtonElement>;
}

interface Footnote {
  n: number;
  source: Source;
}

/** Assigns footnote numbers to sources in order of first use; one number per file:line. */
class FootnoteBook {
  private byKey = new Map<string, Footnote>();
  readonly list: Footnote[] = [];
  ref(source: Source): number {
    const key = `${cite(source)}#${source.sha256}`;
    let f = this.byKey.get(key);
    if (!f) {
      f = { n: this.list.length + 1, source };
      this.byKey.set(key, f);
      this.list.push(f);
    }
    return f.n;
  }
}

function Marks({ ns }: { ns: number[] }) {
  const unique = [...new Set(ns)].sort((a, b) => a - b);
  if (unique.length === 0) return null;
  return (
    <>
      {unique.map((n, i) => (
        <Fragment key={n}>
          <a className="inv-fn" href={`#inv-fn-${n}`} aria-label={`Source ${n}`}>
            {i === 0 ? "" : ","}
            {n}
          </a>
        </Fragment>
      ))}
    </>
  );
}

/** A printable case report where every evidence-backed sentence is footnoted to file:line and sha256. */
export function CaseReport({ findings, onClose, closeRef }: CaseReportProps) {
  const model = useMemo(() => {
    const book = new FootnoteBook();
    const persons = new Map<string, Person>(findings.persons.map((p) => [p.id, p]));
    const eventsById = new Map<string, EventRec>(findings.events.map((e) => [e.id, e]));
    const verifiedIds = new Set(findings.verification.verified_event_ids ?? []);
    const timeline = findings.events
      .filter((e) => e.verified || verifiedIds.has(e.id))
      .slice()
      .sort((a, b) => (a.t < b.t ? -1 : a.t > b.t ? 1 : 0))
      .map((e) => ({ e, n: book.ref(e.source), who: eventActorLabel(e, persons) }));

    const sourcesFor = (eventIds: string[]) =>
      eventIds.flatMap((id) => {
        const e = eventsById.get(id);
        return e ? [book.ref(e.source)] : [];
      });

    const contradictions = findings.contradictions
      .slice()
      .sort((a, b) => b.score - a.score)
      .map((c) => ({ c, ns: sourcesFor(c.events) }));
    const cById = new Map(findings.contradictions.map((c) => [c.id, c]));

    const hypotheses = findings.hypotheses
      .slice()
      .sort((a, b) => b.confidence - a.confidence)
      .map((h) => ({ h, ns: sourcesFor(h.supports.flatMap((id) => cById.get(id)?.events ?? [])) }));

    return { book, timeline, contradictions, hypotheses };
  }, [findings]);

  const v = findings.verification;
  const rejected = v.rejected.length;
  const verifiedPct = v.claims > 0 ? Math.round((v.verified / v.claims) * 100) : null;

  return (
    <>
      <div className="inv-report-toolbar">
        <button type="button" className="inv-btn inv-btn-red" onClick={() => window.print()}>
          Export PDF
        </button>
        {onClose && (
          <button type="button" className="inv-btn" onClick={onClose} ref={closeRef}>
            Close report
          </button>
        )}
      </div>

      <article className="inv-report" aria-labelledby="inv-report-title">
        <header>
          <p className="inv-report-meta">Princeton Files</p>
          <h1 id="inv-report-title">{findings.case.title}</h1>
          <p className="inv-report-meta">{findings.case.address}</p>
          <p>{findings.case.summary}</p>
          <p>
            The agents made {v.claims} claims. The verifier confirmed {v.verified}
            {verifiedPct !== null ? ` (${verifiedPct}%)` : ""} against a quoted, hashed source line and rejected{" "}
            {rejected}. This report lists facts and contradictions only; it makes no finding of fault.
          </p>
        </header>

        <section aria-labelledby="inv-r-timeline">
          <h2 id="inv-r-timeline">Timeline of verified events</h2>
          {model.timeline.length === 0 ? (
            <p>No events have been verified yet.</p>
          ) : (
            <table className="inv-report-table">
              <thead>
                <tr>
                  <th scope="col">Time as written</th>
                  <th scope="col">Event</th>
                  <th scope="col">Quote from the source</th>
                </tr>
              </thead>
              <tbody>
                {model.timeline.map(({ e, n, who }) => (
                  <tr key={e.id}>
                    <td className="inv-t">{formatTimeAsWritten(e.t)}</td>
                    <td>
                      {humanize(e.type)}
                      {who ? `, ${who}` : ""}
                      {e.room ? `, room ${e.room}` : ""}
                      {e.device ? `, device ${e.device}` : ""}.
                      <Marks ns={[n]} />
                    </td>
                    <td>
                      <q>{e.source.quote}</q>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section aria-labelledby="inv-r-contra">
          <h2 id="inv-r-contra">Contradictions</h2>
          {model.contradictions.length === 0 ? (
            <p>No contradictions were found in the verified events.</p>
          ) : (
            model.contradictions.map(({ c, ns }) => (
              <div key={c.id}>
                <h3>
                  {c.id}: {c.kind}, score {c.score.toFixed(2)}
                </h3>
                <p>
                  {c.explanation}
                  <Marks ns={ns} />
                </p>
              </div>
            ))
          )}
        </section>

        <section aria-labelledby="inv-r-hyp">
          <h2 id="inv-r-hyp">Hypotheses, ranked</h2>
          {model.hypotheses.length === 0 ? (
            <p>The investigator has not proposed any hypotheses.</p>
          ) : (
            <ol>
              {model.hypotheses.map(({ h, ns }) => (
                <li key={h.id}>
                  <p>
                    {h.text} Confidence {pct(h.confidence)}%
                    {h.supports.length > 0 ? `, resting on ${h.supports.join(", ")}` : ""}.
                    <Marks ns={ns} />
                  </p>
                  <p>
                    <em>What would disprove this:</em> {h.disproved_by || "not stated."}
                  </p>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section aria-labelledby="inv-r-evidence">
          <h2 id="inv-r-evidence">Evidence files</h2>
          {findings.evidence.length === 0 ? (
            <p>No evidence files are listed.</p>
          ) : (
            <table className="inv-report-table">
              <thead>
                <tr>
                  <th scope="col">File</th>
                  <th scope="col">sha256</th>
                  <th scope="col">Custody</th>
                  <th scope="col">Records</th>
                </tr>
              </thead>
              <tbody>
                {findings.evidence.map((ev) => (
                  <tr key={ev.file}>
                    <td className="inv-report-quote">{ev.file}</td>
                    <td className="inv-report-quote">{shortSha(ev.sha256)}</td>
                    <td>{ev.manifest_match ? "Matches manifest" : "Does not match manifest, not trusted"}</td>
                    <td>{ev.records}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section aria-labelledby="inv-r-notes">
          <h2 id="inv-r-notes">Sources</h2>
          {model.book.list.length === 0 ? (
            <p>No sources cited.</p>
          ) : (
            <ol className="inv-footnotes">
              {model.book.list.map(({ n, source }) => (
                <li key={n} id={`inv-fn-${n}`}>
                  {cite(source)}, sha256 {shortSha(source.sha256)}: <q>{source.quote}</q>
                </li>
              ))}
            </ol>
          )}
        </section>
      </article>
    </>
  );
}
