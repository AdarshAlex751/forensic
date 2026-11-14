import { createContext, useContext, type ComponentType, type ReactNode } from "react";

// Slots come from context (set in App.tsx), so pages never import each other or the registry.
const SlotsContext = createContext<Record<string, ComponentType>>({});

export function SlotsProvider({ value, children }: { value: Record<string, ComponentType>; children: ReactNode }) {
  return <SlotsContext.Provider value={value}>{children}</SlotsContext.Provider>;
}

export function Slot({ name }: { name: string }) {
  const Component = useContext(SlotsContext)[name];
  return Component ? <Component /> : <div className="text-sm text-red-700">Empty slot: {name}</div>;
}
