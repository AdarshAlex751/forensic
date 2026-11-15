import { ScenePage } from "../scene/ScenePage";
import { PaperShell } from "./PaperShell";

// Route "/scene": the unchanged ScenePage inside the shared golden-paper frame. ScenePage is never re-keyed or
// conditionally wrapped, so the Matterport iframe it creates is not reloaded by anything in here.
export function ScenePaperShell() {
  return (
    <PaperShell label="Scene">
      <ScenePage />
    </PaperShell>
  );
}
