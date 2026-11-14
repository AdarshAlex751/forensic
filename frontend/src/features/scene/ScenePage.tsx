import { Slot } from "../../shared/Slot";
import { useFindings } from "../../shared/useFindings";

// Placeholder (Person 2): aerial, Matterport, timeline. Mounts the Red flags panel via a slot.
export function ScenePage() {
  const { data } = useFindings();
  return (
    <section className="grid gap-6 md:grid-cols-[2fr_1fr]">
      <div>
        <h1 className="mb-2 text-xl">Scene</h1>
        <p>
          Matterport model {data?.case.matterport_model_id}: {data?.events.length ?? 0} events, {data?.devices.length ?? 0} devices.
        </p>
      </div>
      <Slot name="scene.red-flags" />
    </section>
  );
}
