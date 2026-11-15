import { useEffect, useState } from "react";

// Placeholder (Person 2): judge mode toggle, mounted by the layout on every page.
export function JudgeMode() {
  const [on, setOn] = useState(false);
  const [text, setText] = useState("Loading evaluation...");
  useEffect(() => {
    if (!on) return;
    const controller = new AbortController();
    setText("Loading evaluation...");
    fetch("/api/scene/evaluation", { signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error();
      const result = await response.json();
      setText(["complete", "evaluated"].includes(result.status)
        ? `${result.found}/${result.planted} found; ${result.false_alarms} false alarms`
        : result.reason || result.message || "Awaiting the current case answer key and source-matched findings.");
    }).catch(() => { if (!controller.signal.aborted) setText("Evaluation unavailable. Check the scene backend."); });
    return () => controller.abort();
  }, [on]);
  return (
    <div className="relative">
      <button className="text-sm underline" aria-expanded={on} onClick={() => setOn(!on)}>Judge mode</button>
      {on && <aside className="absolute right-0 top-8 z-50 w-80 rounded border border-stone-600 bg-stone-900 p-5 shadow-xl" aria-label="Case evaluation">
        <h2 className="text-lg">Case evaluation</h2><p role="status">{text}</p>
        <button className="mt-3 underline" onClick={() => setOn(false)}>Close</button>
      </aside>}
    </div>
  );
}
