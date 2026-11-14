import { useCallback, useEffect, useRef, useState } from "react";
import type { TraceEvent, TraceStatus, TraceTodo } from "./AgentTrace";

const STREAM_URL = "/api/investigator/stream";
const MAX_EVENTS = 300;

function parseTrace(raw: string): TraceEvent | null {
  try {
    const d = JSON.parse(raw) as Partial<TraceEvent>;
    if (typeof d.msg !== "string" || typeof d.agent !== "string") return null;
    return {
      seq: typeof d.seq === "number" ? d.seq : Date.now(),
      agent: d.agent,
      stage: (d.stage ?? "plan") as TraceEvent["stage"],
      msg: d.msg,
      todos: Array.isArray(d.todos) ? d.todos : undefined,
    };
  } catch {
    return null;
  }
}

export interface AgentTraceState {
  events: TraceEvent[];
  todos: TraceTodo[] | undefined;
  status: TraceStatus;
  /** True while the stream is open and delivering. */
  connected: boolean;
  /** True when there is no open stream (never opened, 404, or finished). */
  idle: boolean;
  /** Opens the stream again, e.g. after an approval starts a new run. */
  reconnect: () => void;
}

/**
 * Subscribes to the investigator agent stream via EventSource. Never invents
 * activity: if the stream is missing (404, fake mode) the state is simply idle.
 */
export function useAgentTrace(): AgentTraceState {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [todos, setTodos] = useState<TraceTodo[] | undefined>(undefined);
  const [status, setStatus] = useState<TraceStatus>("connecting");
  const [attempt, setAttempt] = useState(0);
  const seen = useRef(new Set<number>());

  useEffect(() => {
    if (typeof EventSource === "undefined") {
      setStatus("idle");
      return;
    }
    // Each connection starts a fresh log; the server may replay the run from seq 1.
    seen.current = new Set<number>();
    setEvents([]);
    setTodos(undefined);
    setStatus("connecting");
    const es = new EventSource(STREAM_URL);
    es.onopen = () => setStatus("connected");
    es.onmessage = (m: MessageEvent<string>) => {
      const ev = parseTrace(m.data);
      if (!ev || seen.current.has(ev.seq)) return;
      seen.current.add(ev.seq);
      setStatus("connected");
      setEvents((prev) => {
        const next = [...prev, ev];
        return next.length > MAX_EVENTS ? next.slice(next.length - MAX_EVENTS) : next;
      });
      if (ev.todos) setTodos(ev.todos);
    };
    // A closed or missing stream is not retried automatically: that would look like activity.
    es.onerror = () => {
      es.close();
      setStatus("idle");
    };
    return () => es.close();
  }, [attempt]);

  const reconnect = useCallback(() => setAttempt((n) => n + 1), []);

  return {
    events,
    todos,
    status,
    connected: status === "connected",
    idle: status === "idle",
    reconnect,
  };
}
