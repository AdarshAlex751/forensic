import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { Slot } from "./Slot";

// Page list is fixed in the skeleton; keep in step with registry.ts pages.
// The Summary page (/summary) is registered but intentionally not listed here: the app goes Desk -> Scene.
const NAV = [
  { to: "/", label: "Desk" },
  { to: "/scene", label: "Scene" },
  { to: "/yarn", label: "Yarn board" },
  { to: "/memo", label: "Investigator memo" },
];

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-stone-900 text-stone-100">
      <header className="flex items-center gap-4 border-b border-stone-700 px-4 py-2">
        <span className="font-mono text-sm tracking-widest">CASE #1010F</span>
        <nav className="flex gap-3 text-sm">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => (isActive ? "underline" : "opacity-70")}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto">
          <Slot name="layout.judge-mode" />
        </div>
      </header>
      <main className="p-4">{children}</main>
    </div>
  );
}
