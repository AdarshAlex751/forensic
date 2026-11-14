import { create } from "zustand";

// The only cross-slice frontend state (CONTRACTS rule 10). Do not add keys without the Integrator.
interface UiState {
  selectedEventId: string | null;
  selectedContradictionId: string | null;
  timelineTime: string | null; // ISO 8601 with offset
  selectedPersonId: string | null;
  setSelectedEventId: (id: string | null) => void;
  setSelectedContradictionId: (id: string | null) => void;
  setTimelineTime: (t: string | null) => void;
  setSelectedPersonId: (id: string | null) => void;
}

export const useStore = create<UiState>((set) => ({
  selectedEventId: null,
  selectedContradictionId: null,
  timelineTime: null,
  selectedPersonId: null,
  setSelectedEventId: (selectedEventId) => set({ selectedEventId }),
  setSelectedContradictionId: (selectedContradictionId) => set({ selectedContradictionId }),
  setTimelineTime: (timelineTime) => set({ timelineTime }),
  setSelectedPersonId: (selectedPersonId) => set({ selectedPersonId }),
}));
