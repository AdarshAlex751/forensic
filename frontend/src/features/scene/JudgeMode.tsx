import { useState } from "react";
import { useFindings } from "../../shared/useFindings";

// Placeholder (Person 2): judge mode toggle, mounted by the layout on every page.
export function JudgeMode() {
  const [on, setOn] = useState(false);
  const { data } = useFindings();
  return (
    <button className="text-sm underline" onClick={() => setOn(!on)}>
      {on && data ? `Judge: ${data.eval.found}/${data.eval.planted} found, ${data.eval.false_alarms} false alarms` : "Judge mode"}
    </button>
  );
}
