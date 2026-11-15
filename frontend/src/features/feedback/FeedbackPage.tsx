import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useFindings } from "../../shared/useFindings";
import { PaperShell } from "../opening/PaperShell";
import { blockLength, blockText, useTypewriter } from "./useTypewriter";
import type { Block, Part } from "./useTypewriter";
import "./feedback.css";

// ---------- data: GET /api/feedback ----------
interface Quote { event: string; file: string; line: number; quote: string }
interface Question {
  id: string;
  kind: string;
  kind_label: string;
  question: string;
  why: string;
  cites: { events?: string[]; contradictions?: string[]; persons?: string[] };
  quotes: Quote[];
  focus: string | null;
}
interface FeedbackData {
  case_id: string;
  generated_at: string;
  source: string;
  model: string;
  questions: Question[];
  counts: { asked: number; kept: number; rejected: number };
  warnings: unknown[];
}

async function getFeedback(): Promise<FeedbackData> {
  const r = await fetch("/api/feedback");
  if (!r.ok) throw new Error(`feedback request failed: ${r.status}`);
  const j = (await r.json()) as Partial<FeedbackData>;
  const questions = Array.isArray(j.questions) ? j.questions : [];
  return {
    case_id: j.case_id ?? "",
    generated_at: j.generated_at ?? "",
    source: j.source ?? "",
    model: j.model ?? "",
    questions,
    counts: j.counts ?? { asked: questions.length, kept: questions.length, rejected: 0 },
    warnings: Array.isArray(j.warnings) ? j.warnings : [],
  };
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const REGENERATE_WAIT_MS = 90_000;

// Letters already typed this session (by generation time): coming back to the tab shows the finished letter at once.
const typedBefore = new Set<string>();
const prefersReducedMotion = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// A classic double-loop paperclip, drawn as one wire (viewBox 8 8 50 64).
const CLIP_PATH = "M50 14 V50 a18 18 0 0 1 -36 0 V26 a9 9 0 0 1 18 0 V46 a5 5 0 0 0 10 0 V30";

// ---------- the letter ----------
const MAX_EVENT_TAGS = 8;

function buildLetter(fb: FeedbackData, nameOf: (personId: string) => string): Block[] {
  const blocks: Block[] = [
    { id: "greet", cls: "fb-greet", parts: [{ text: "Dear Investigator:" }] },
    { id: "intro", cls: "fb-p", parts: [{ text: "The following questions may sharpen the investigation. Answering them is optional." }] },
  ];
  if (fb.questions.length === 0) blocks.push({ id: "none", cls: "fb-p", parts: [{ text: "No questions at this time." }] });

  fb.questions.forEach((q, i) => {
    blocks.push({ id: `${q.id}-q`, cls: "fb-q", parts: [{ text: `${i + 1}. ` }, { text: q.kind_label, cls: "hl" }, { text: `  ${q.question}` }] });
    if (q.why) blocks.push({ id: `${q.id}-why`, cls: "fb-why", parts: [{ text: q.why, cls: "dim" }] });

    const events = q.cites.events ?? [];
    const tags = [
      ...events.slice(0, MAX_EVENT_TAGS),
      ...(events.length > MAX_EVENT_TAGS ? [`+${events.length - MAX_EVENT_TAGS} more events`] : []),
      ...(q.cites.contradictions ?? []),
      ...(q.cites.persons ?? []).map(nameOf),
    ];
    if (tags.length) {
      const parts: Part[] = tags.flatMap((t, k) => [{ text: `[${t}]`, cls: "tag" }, ...(k < tags.length - 1 ? [{ text: " " }] : [])]);
      blocks.push({ id: `${q.id}-tags`, cls: "fb-tags", parts });
    }
    q.quotes.forEach((s, k) =>
      blocks.push({ id: `${q.id}-quote${k}`, cls: "fb-quote", parts: [{ text: `${s.file}:${s.line}  `, cls: "dim" }, { text: `"${s.quote}"` }] }),
    );
  });

  blocks.push({ id: "bye", cls: "fb-sign", parts: [{ text: "Most sincerely," }] });
  blocks.push({ id: "desk", cls: "fb-sign", parts: [{ text: "Princeton Files Feedback Desk" }] });
  return blocks;
}

// ---------- rendering: a word at a time, each nudged by a stable pseudo-random amount (cheap: no per-character nodes) ----------
const seeded = (n: number) => {
  const x = Math.sin(n * 12.9898) * 43758.5453;
  return x - Math.floor(x);
};
const hash = (s: string) => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) | 0, 7);

function Run({ text, cls, seed }: { text: string; cls?: string; seed: number }) {
  const tokens = text.split(/(\s+)/);
  return (
    <span className={cls ? `fb-${cls}` : undefined}>
      {tokens.map((t, i) =>
        /^\s*$/.test(t) ? (
          t
        ) : (
          <span
            key={i}
            className="fb-w"
            style={{ top: (seeded(seed + i) - 0.5) * 1.4, left: (seeded(seed + i + 0.5) - 0.5) * 1.2, opacity: 0.84 + seeded(seed + i + 0.25) * 0.14 }}
          >
            {t}
          </span>
        ),
      )}
    </span>
  );
}

const BlockView = memo(function BlockView({ block, chars, caret }: { block: Block; chars: number; caret: boolean }) {
  let left = chars;
  const out: ReactNode[] = [];
  block.parts.forEach((part, i) => {
    if (left <= 0) return;
    out.push(<Run key={i} text={part.text.slice(0, left)} cls={part.cls} seed={hash(block.id) + i * 101} />);
    left -= part.text.length;
  });
  return (
    <p className={`fb-line ${block.cls}`}>
      {out}
      {caret && <span className="fb-caret" aria-hidden="true" />}
    </p>
  );
});

/** A single short typed line with the caret (loading and status messages). */
function TypedLine({ text, className }: { text: string; className?: string }) {
  const blocks = useMemo<Block[]>(() => [{ id: "line", cls: className ?? "fb-p", parts: [{ text }] }], [text, className]);
  const { pos, done } = useTypewriter(blocks, { instant: prefersReducedMotion(), resetKey: text });
  return <BlockView block={blocks[0]} chars={done ? blockLength(blocks[0]) : pos.chars} caret={!done} />;
}

// ---------- the page ----------
export function FeedbackPage() {
  const { data: findings, error: findingsError } = useFindings();
  const [fb, setFb] = useState<FeedbackData | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [refresh, setRefresh] = useState<"idle" | "working" | "failed">("idle");
  const scrollRef = useRef<HTMLDivElement>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  // The typewriter face is loaded only while this page is open.
  useEffect(() => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "https://fonts.googleapis.com/css2?family=Special+Elite&family=Courier+Prime:wght@400;700&display=swap";
    link.dataset.fbFont = "true";
    document.head.appendChild(link);
    return () => link.remove();
  }, []);

  useEffect(() => {
    getFeedback()
      .then((d) => alive.current && setFb(d))
      .catch(() => alive.current && setLoadFailed(true));
  }, []);

  // Person ids become names when the findings have them; wait for the findings (or their failure) so tags do not change mid-letter.
  const namesReady = Boolean(findings) || Boolean(findingsError);
  const names = useMemo(() => new Map((findings?.persons ?? []).map((p) => [p.id, p.name])), [findings]);
  const blocks = useMemo(() => (fb && namesReady ? buildLetter(fb, (id) => names.get(id) ?? id) : []), [fb, namesReady, names]);

  const key = fb ? `${fb.generated_at}|${fb.source}|${fb.questions.length}` : "";
  const instant = prefersReducedMotion() || (key !== "" && typedBefore.has(key));
  // Typing (re)starts when the letter exists: the questions can arrive before the person names, and then the key alone
  // would not change when the letter is finally built.
  const { pos, done, skip } = useTypewriter(blocks, { instant, resetKey: blocks.length ? key : "", onFinish: () => key && typedBefore.add(key) });

  // Keep the caret in view only if the reader is already near the bottom.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || done) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 200) el.scrollTop = el.scrollHeight;
  }, [pos.block, pos.chars >> 4, done]);

  const regenerate = useCallback(async () => {
    if (!fb || refresh === "working") return;
    setRefresh("working");
    const previous = fb.generated_at;
    try {
      const r = await fetch("/api/feedback/regenerate", { method: "POST" });
      if (!r.ok) throw new Error(`regenerate failed: ${r.status}`);
      const deadline = Date.now() + REGENERATE_WAIT_MS;
      while (Date.now() < deadline) {
        await sleep(2000);
        if (!alive.current) return;
        const next = await getFeedback();
        if (next.generated_at !== previous) {
          if (!alive.current) return;
          setFb(next);
          setRefresh("idle");
          return;
        }
      }
      throw new Error("timed out");
    } catch {
      if (alive.current) setRefresh("failed"); // the previous questions stay on the sheet
    }
  }, [fb, refresh]);

  const ready = Boolean(fb) && namesReady;
  const plain = useMemo(() => blocks.map(blockText).join("\n"), [blocks]);

  return (
    <PaperShell label="Feedback">
      <div className="fb-page">
        <div className="fb-scroll" ref={scrollRef}>
          {fb && fb.warnings.length > 0 && (
            <div className="fb-warnings">
              {fb.warnings.map((w, i) => (
                <small key={i} className="fb-warn">{typeof w === "string" ? w : JSON.stringify(w)}</small>
              ))}
            </div>
          )}

          <article className="fb-sheet paper-gold" onClick={() => ready && !done && skip()} aria-label="Questions for the investigator">
            {/* a paperclip over the top-left edge of the sheet: decoration only, out of the layout */}
            <svg className="fb-clip" viewBox="8 8 50 64" aria-hidden="true" focusable="false">
              <defs>
                <linearGradient id="fb-clip-grad" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0" stopColor="#ffffff" />
                  <stop offset="0.5" stopColor="#cfd5d9" />
                  <stop offset="1" stopColor="#f6f8f9" />
                </linearGradient>
              </defs>
              {/* a darker underlay gives the silver wire an edge against the paper, then the bright wire on top */}
              <path d={CLIP_PATH} fill="none" stroke="#98a0a6" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
              <path d={CLIP_PATH} fill="none" stroke="url(#fb-clip-grad)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {ready && !done && (
              <button type="button" className="fb-skip" onClick={(e) => { e.stopPropagation(); skip(); }}>
                [skip]
              </button>
            )}

            {loadFailed ? (
              <TypedLine text="Could not reach the case file. Start the backend and reload this page." />
            ) : !ready ? (
              <TypedLine text="Reading the case file..." />
            ) : (
              <>
                {/* screen readers get the whole letter at once; the typing is only for the eyes */}
                {!done && <div className="fb-sr" role="document">{plain}</div>}
                <div aria-hidden={!done ? true : undefined}>
                  {blocks.map((b, i) => {
                    if (i > pos.block) return null;
                    const active = i === pos.block;
                    return <BlockView key={b.id} block={b} chars={active ? pos.chars : blockLength(b)} caret={active && !done} />;
                  })}
                </div>

                {done && (
                  <div className="fb-actions">
                    <button type="button" className="fb-btn" onClick={() => void regenerate()} disabled={refresh === "working"}>
                      [ Regenerate questions ]
                    </button>
                    {refresh === "working" && <TypedLine text="Re-reading the case..." className="fb-calm" />}
                    {refresh === "failed" && <TypedLine text="Could not refresh. Showing the previous questions." className="fb-calm" />}
                  </div>
                )}
              </>
            )}
          </article>
        </div>
      </div>
    </PaperShell>
  );
}
