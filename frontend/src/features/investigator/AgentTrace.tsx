import { useEffect, useRef } from "react";
import "./investigator.css";

export type TraceAgent = "lead" | "timeline" | "physics" | "comms" | "money" | "verifier";
export type TraceStage = "verify" | "plan" | "delegate" | "rank" | "request" | "replan" | "done";
export type TodoStatus = "pending" | "doing" | "done";

export interface TraceTodo {
  text: string;
  status: TodoStatus;
}

/** One message from `/api/investigator/stream`. */
export interface TraceEvent {
  seq: number;
  agent: TraceAgent;
  stage: TraceStage;
  msg: string;
  todos?: TraceTodo[];
}

/** Connection state of the trace stream. */
export type TraceStatus = "connecting" | "connected" | "idle";

export interface AgentTraceProps {
  events: TraceEvent[];
  /** Latest to-do list; falls back to the last event that carried one. */
  todos?: TraceTodo[];
  status?: TraceStatus;
}

const SUBAGENTS: readonly TraceAgent[] = ["timeline", "physics", "comms", "money"];

const TODO_MARK: Record<TodoStatus, string> = { pending: "[ ]", doing: "[>]", done: "[x]" };
const TODO_WORD: Record<TodoStatus, string> = { pending: "Pending", doing: "In progress", done: "Done" };

/** Live log of the investigator agents, their to-do list and which subagent is working. */
export function AgentTrace({ events, todos, status = "idle" }: AgentTraceProps) {
  const logRef = useRef<HTMLOListElement>(null);
  const last = events.length > 0 ? events[events.length - 1] : undefined;
  const list = todos ?? [...events].reverse().find((e) => e.todos && e.todos.length > 0)?.todos ?? [];
  const working = last && last.stage !== "done" ? last.agent : null;

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events.length]);

  const statusText =
    status === "connected"
      ? working
        ? `Live. ${working === "lead" ? "The lead agent" : `The ${working} agent`} is working.`
        : "Live. Waiting for the agents."
      : status === "connecting"
        ? "Connecting to the agent stream…"
        : events.length > 0
          ? "Run finished. The stream is closed."
          : "No agent run is in progress.";

  return (
    <div>
      <p className="inv-status-line" role="status">
        <span className={status === "connected" ? "inv-dot inv-is-live" : "inv-dot"} aria-hidden="true" />
        {statusText}
      </p>

      {events.length === 0 ? (
        <p className="inv-state">
          Nothing to show yet. The agents report here while they work, for example after you approve an evidence
          request.
        </p>
      ) : (
        <>
          <ul className="inv-trace-agents" aria-label="Subagents">
            {SUBAGENTS.map((a) => (
              <li key={a} className={a === working ? "inv-trace-agent inv-is-active" : "inv-trace-agent"}>
                {a}
                {a === working && <span className="inv-sr-only"> (working)</span>}
              </li>
            ))}
          </ul>

          {list.length > 0 && (
            <ul className="inv-todos" aria-label="Agent to-do list">
              {list.map((t, i) => (
                <li key={`${i}-${t.text}`} className={`inv-todo-${t.status}`}>
                  <span aria-hidden="true">{TODO_MARK[t.status]}</span>
                  <span>
                    <span className="inv-sr-only">{TODO_WORD[t.status]}: </span>
                    {t.text}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <ol ref={logRef} className="inv-log" aria-label="Agent log" aria-live="polite" tabIndex={0}>
            {events.map((e) => (
              <li key={e.seq}>
                <span className="inv-log-who">
                  {e.agent}/{e.stage}
                </span>
                <span className="inv-log-msg">{e.msg}</span>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
