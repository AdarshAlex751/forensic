// Frontend registry: the only place that knows which slice provides which page or panel.
// Not edited after the skeleton. Owners replace the component inside their own folder.
import type { ComponentType } from "react";
import { RedFlagsPanel } from "./features/analysis/RedFlagsPanel";
import { YarnPage } from "./features/analysis/YarnPage";
import { Desk } from "./features/evidence/Desk";
import { SummaryPage } from "./features/evidence/SummaryPage";
import { InvestigatorMemo } from "./features/investigator/InvestigatorMemo";
import { JudgeMode } from "./features/scene/JudgeMode";
import { ScenePage } from "./features/scene/ScenePage";

export interface PageDef {
  path: string;
  label: string;
  component: ComponentType;
}

export const pages: PageDef[] = [
  { path: "/", label: "Desk", component: Desk },
  { path: "/summary", label: "Summary", component: SummaryPage },
  { path: "/scene", label: "Scene", component: ScenePage },
  { path: "/yarn", label: "Yarn board", component: YarnPage },
];

// Slots: screens that combine two people's work. Pages render <Slot name="..." />.
export const slots: Record<string, ComponentType> = {
  "scene.red-flags": RedFlagsPanel, // Scene page (Person 2) shows Red flags (Person 3)
  "yarn.memo": InvestigatorMemo, // Yarn page (Person 3) shows Memo (Person 4)
  "layout.judge-mode": JudgeMode, // mounted by the layout on every page (Person 2)
};
