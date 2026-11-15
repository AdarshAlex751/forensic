import { useEffect } from "react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { Slot } from "../../shared/Slot";
import "./paper.css";
import "./scene-skin.css";

// Mirrors the NAV array in shared/layout.tsx (the Summary tab stays hidden in both).
const NAV = [
  { to: "/", label: "Desk" },
  { to: "/scene", label: "Scene" },
  { to: "/red-flags", label: "Red flags" },
  { to: "/contradictions", label: "Contradictions" },
  { to: "/memo", label: "Investigator memo" },
  { to: "/feedback", label: "Feedback" },
];

/**
 * The golden-paper page frame shared by /scene, /red-flags, /contradictions and /memo: a full-screen layer on the same
 * paper the opening zoom lands on (so every handover is invisible), covering the shared header (as the opening does),
 * with its own slim top bar and the Judge-mode slot. The children are rendered as they are and never re-keyed, so a
 * page that owns an iframe (the Matterport tour) is not reloaded by anything in here. Styles: scene-skin.css.
 */
export function PaperShell({ label, children }: { label: string; children: ReactNode }) {
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  return (
    <div className="scene-paper paper-gold paper-gold--edge" role="region" aria-label={label}>
      <header className="sp-bar">
        <span className="sp-case">CASE #1010F</span>
        <nav className="sp-nav" aria-label="Pages">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) => (isActive ? "sp-link sp-link--on" : "sp-link")}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="sp-judge">
          <Slot name="layout.judge-mode" />
        </div>
      </header>
      <div className="sp-body">{children}</div>
    </div>
  );
}
