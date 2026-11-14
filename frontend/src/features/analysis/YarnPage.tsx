import { Slot } from "../../shared/Slot";
import { useFindings } from "../../shared/useFindings";

// Placeholder (Person 3): the red yarn board. Mounts the investigator memo via a slot.
export function YarnPage() {
  const { data } = useFindings();
  return (
    <section className="grid gap-6 md:grid-cols-2">
      <div>
        <h1 className="mb-2 text-xl">Yarn board</h1>
        <ul>
          {data?.persons.map((p) => (
            <li key={p.id}>
              {p.name}: anomaly {p.anomaly.toFixed(2)}
            </li>
          ))}
        </ul>
      </div>
      <Slot name="yarn.memo" />
    </section>
  );
}
