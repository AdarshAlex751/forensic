import { useEffect } from "react";
import { NavLink } from "react-router-dom";
import { Slot } from "../../shared/Slot";
import { ScenePage } from "../scene/ScenePage";
import "./paper.css";
import "./scene-skin.css";

// Mirrors the NAV array in shared/layout.tsx. The Summary tab is intentionally hidden there, so it is hidden here too.
const NAV = [
  { to: "/", label: "Desk" },
  { to: "/scene", label: "Scene" },
  { to: "/yarn", label: "Yarn board" },
  { to: "/memo", label: "Investigator memo" },
];

// Route "/scene". A full-screen layer on the same golden paper the opening zoom lands on, so the handover from the
// opening is invisible. It covers the shared header (as the opening does) and carries its own slim top bar.
// <ScenePage /> is rendered unchanged and is never re-keyed or conditionally wrapped, so the Matterport iframe it
// creates is not reloaded by anything in here. Every style lives in scene-skin.css under .scene-paper.
export function ScenePaperShell() {
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  return (
    <div className="scene-paper paper-gold paper-gold--edge" role="region" aria-label="Scene">
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
      <div className="sp-body">
        <ScenePage />
      </div>
    </div>
  );
}
