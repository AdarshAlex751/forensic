// Frontend registry: the only place that knows which slice provides which page or panel.
// Not edited after the skeleton. Owners replace the component inside their own folder.
import type { ComponentType } from "react";
import { RedFlagsPanel } from "./features/analysis/RedFlagsPanel";
import { YarnPage } from "./features/analysis/YarnPage";
import { OpeningScreen } from "./features/opening/OpeningScreen";
import { SummaryPage } from "./features/evidence/SummaryPage";
import { InvestigatorMemo } from "./features/investigator/InvestigatorMemo";
import { JudgeMode } from "./features/scene/JudgeMode";
import { ScenePaperShell } from "./features/opening/ScenePaperShell";

export interface PageDef {
  path: string;
  label: string;
  component: ComponentType;
}

export const pages: PageDef[] = [
  { path: "/", label: "Desk", component: OpeningScreen },
  // The Summary tab is intentionally hidden from the top bar (see shared/layout.tsx); the page stays reachable by URL.
  { path: "/summary", label: "Summary", component: SummaryPage },
  { path: "/scene", label: "Scene", component: ScenePaperShell }, // wraps ScenePage (Person 2) in the paper skin
  { path: "/yarn", label: "Yarn board", component: YarnPage },
  { path: "/memo", label: "Investigator memo", component: InvestigatorMemo },
];

// Slots: screens that combine two people's work. Pages render <Slot name="..." />.
export const slots: Record<string, ComponentType> = {
  "scene.red-flags": RedFlagsPanel, // Scene page (Person 2) shows Red flags (Person 3)
  "yarn.memo": InvestigatorMemo, // Yarn page (Person 3) shows Memo (Person 4)
  "layout.judge-mode": JudgeMode, // mounted by the layout on every page (Person 2)
};
