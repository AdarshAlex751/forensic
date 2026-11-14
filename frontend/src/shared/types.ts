// Mirrors backend/app/shared/schema.py (from the findings.json schema in docs/PLAN.md).
export interface Source { file: string; line: number; quote: string; sha256: string }
export interface CaseInfo { id: string; title: string; address: string; summary: string; costar_property_id: string; matterport_model_id: string }
export interface Evidence { file: string; sha256: string; manifest_match: boolean; parser: string; records: number }
export interface Person { id: string; name: string; role: string; suite: string; aliases: string[]; anomaly: number; features: Record<string, number>; community: number }
export interface Device { id: string; type: string; room: string; sweep: string; tag_xyz: [number, number, number] }
export interface Room { id: string; label: string; floor: number }
export interface EventRec { id: string; t: string; type: string; person: string | null; device: string | null; room: string | null; source: Source; verified: boolean }
export interface Edge { from: string; to: string; type: string; events: string[] }
export type ContradictionKind = "physical" | "temporal" | "statement" | "custody";
export interface Contradiction { id: string; kind: ContradictionKind; events: string[]; score: number; explanation: string; path?: string[]; walk_s?: number; gap_s?: number }
export interface Hypothesis { id: string; text: string; confidence: number; supports: string[]; disproved_by: string }
export interface EvidenceRequest { id: string; ask: string; why: string; status: "pending" | "approved" | "ingested" }
export interface Note { text: string; kind: "check_next" | "todo" | "cleared" }
export interface Verification { claims: number; verified: number; rejected: { claim: string; reason: string }[]; verified_event_ids?: string[] }
export interface Eval { planted: number; found: number; false_alarms: number; runtime_s: number; missed?: { id: string; why: string }[] }

export interface Findings {
  case: CaseInfo;
  evidence: Evidence[];
  persons: Person[];
  devices: Device[];
  rooms: Room[];
  events: EventRec[];
  edges: Edge[];
  contradictions: Contradiction[];
  hypotheses: Hypothesis[];
  requests: EvidenceRequest[];
  notes: Note[];
  verification: Verification;
  eval: Eval;
}
