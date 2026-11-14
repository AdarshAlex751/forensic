import { useFindings } from "../../shared/useFindings";
import { EvidenceLocker } from "./EvidenceLocker";

// Placeholder (Person 1): case summary spread, person polaroids and the Evidence Locker.
export function SummaryPage() {
  const { data } = useFindings();
  return (
    <section className="grid gap-6 md:grid-cols-2">
      <div>
        <h1 className="mb-2 text-xl">{data?.case.title ?? "Case summary"}</h1>
        <p>{data?.case.summary}</p>
      </div>
      <EvidenceLocker />
    </section>
  );
}
