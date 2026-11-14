import { useFindings } from "../../shared/useFindings";

// Placeholder (Person 4): typed memo with hypotheses, what would disprove each, and the verified counter.
export function InvestigatorMemo() {
  const { data } = useFindings();
  if (!data) return null;
  const v = data.verification;
  return (
    <aside>
      <h2 className="mb-1 text-lg">Investigator memo</h2>
      <p className="text-sm">
        {v.claims} claims made, {v.verified} verified, {v.claims - v.verified} rejected
      </p>
      <ul className="mt-2 space-y-1 text-sm">
        {data.hypotheses.map((h) => (
          <li key={h.id}>
            {h.text} ({Math.round(h.confidence * 100)}%). Disproved by: {h.disproved_by}
          </li>
        ))}
      </ul>
    </aside>
  );
}
