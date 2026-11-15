import type { Findings } from "../../shared/types";
import type { TraceEvent, TraceTodo } from "./AgentTrace";

// The parking log is withheld evidence: the investigator is not supposed to know a particular file exists. The backend's
// request and note text can name it ("access/parking_exit.csv"), so the memo shows it generically instead.
const WITHHELD_FILE = /(?:[\w.-]+\/)*parking_exit\.csv/gi;

export const genericText = (text: string): string => text.replace(WITHHELD_FILE, "the parking records");

/** The findings with the withheld file's name replaced by generic wording wherever the memo and report print it. */
export function withGenericNames(f: Findings): Findings {
  return {
    ...f,
    requests: f.requests.map((r) => ({ ...r, ask: genericText(r.ask), why: genericText(r.why) })),
    notes: f.notes.map((n) => ({ ...n, text: genericText(n.text) })),
    hypotheses: f.hypotheses.map((h) => ({ ...h, text: genericText(h.text), disproved_by: genericText(h.disproved_by) })),
  };
}

/** The agent-activity stream carries the same wording ("Provide access/parking_exit.csv ..."), so it gets the same rewrite. */
export function genericTrace(events: TraceEvent[]): TraceEvent[] {
  return events.map((e) => ({ ...e, msg: genericText(e.msg), todos: e.todos?.map((t) => ({ ...t, text: genericText(t.text) })) }));
}

export function genericTodos(todos: TraceTodo[] | undefined): TraceTodo[] | undefined {
  return todos?.map((t) => ({ ...t, text: genericText(t.text) }));
}
