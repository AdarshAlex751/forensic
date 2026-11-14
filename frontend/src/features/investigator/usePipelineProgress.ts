import { useCallback, useEffect, useRef, useState } from "react";

/** One message from `/api/pipeline/progress`. */
export interface PipelineProgress {
  seq: number;
  running: boolean;
  stage: string | null;
  pct: number;
  msg: string;
}

export type PipelineWatchState = "idle" | "watching" | "done" | "lost";

/**
 * Watches the pipeline SSE after an approval and calls `onFinished` once,
 * when the stream reports `running:false` or closes.
 */
export function usePipelineProgress(onFinished: () => void) {
  const [progress, setProgress] = useState<PipelineProgress | null>(null);
  const [state, setState] = useState<PipelineWatchState>("idle");
  const esRef = useRef<EventSource | null>(null);
  const finishedRef = useRef(onFinished);
  finishedRef.current = onFinished;

  const timerRef = useRef<number | undefined>(undefined);

  const stop = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    window.clearTimeout(timerRef.current);
  }, []);

  useEffect(() => stop, [stop]);

  const watch = useCallback(() => {
    stop();
    if (typeof EventSource === "undefined") {
      setState("lost");
      finishedRef.current();
      return;
    }
    setState("watching");
    setProgress(null);
    let sawRunning = false;
    let finished = false;
    const finish = (s: PipelineWatchState) => {
      if (finished) return;
      finished = true;
      stop();
      setState(s);
      finishedRef.current();
    };
    const es = new EventSource("/api/pipeline/progress");
    esRef.current = es;
    es.onmessage = (m: MessageEvent<string>) => {
      try {
        const p = JSON.parse(m.data) as PipelineProgress;
        setProgress(p);
        if (p.running) sawRunning = true;
        // Ignore a stale "not running" snapshot sent before the rerun has begun.
        else if (sawRunning || p.pct >= 100) finish("done");
      } catch {
        /* skip malformed lines */
      }
    };
    es.onerror = () => finish(sawRunning ? "done" : "lost");
    // If the run never reports as started, stop waiting after 15s and reload anyway.
    timerRef.current = window.setTimeout(() => {
      if (!sawRunning) finish("lost");
    }, 15000);
  }, [stop]);

  return { progress, state, watch };
}
