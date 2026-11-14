import { useFindings } from "../../shared/useFindings";
import { useStore } from "../../shared/store";

// Placeholder (Person 3): slide-out panel of contradiction cards.
export function RedFlagsPanel() {
  const { data } = useFindings();
  const select = useStore((s) => s.setSelectedContradictionId);
  return (
    <aside>
      <h2 className="mb-1 text-lg">Red flags</h2>
      <ul className="space-y-1 text-sm">
        {data?.contradictions.map((c) => (
          <li key={c.id}>
            <button className="text-left" onClick={() => select(c.id)}>
              [{c.kind}] {c.explanation}
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
