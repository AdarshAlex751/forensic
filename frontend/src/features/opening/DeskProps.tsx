import { motion, useReducedMotion } from "framer-motion";
import { useMemo } from "react";
import type { CSSProperties } from "react";

// Pen, paper clips, coffee ring and polaroid. Pure decoration, positioned in percentages.
export function DeskProps({ caption }: { caption: string }) {
  return (
    <>
      <div className="op-prop op-coffee" aria-hidden />

      <svg className="op-prop" style={{ left: "calc(48px + max(40px, 4vw))", bottom: "calc(48px + max(64px, 10vh))", width: "clamp(150px, 18vw, 230px)", transform: "rotate(-24deg)" }} viewBox="0 0 230 26" aria-hidden>
        <rect x="6" y="6" width="196" height="14" rx="7" fill="#14213d" />
        <rect x="6" y="6" width="196" height="5" rx="2.5" fill="#2f4272" opacity=".7" />
        <rect x="150" y="3" width="34" height="3" rx="1.5" fill="#d9ae4f" />
        <rect x="150" y="20" width="34" height="3" rx="1.5" fill="#d9ae4f" />
        <path d="M202 6 L226 13 L202 20 Z" fill="#c9a36a" />
        <path d="M220 11.4 L226 13 L220 14.6 Z" fill="#1a1a1a" />
      </svg>

      <Clip style={{ left: "27%", bottom: "calc(48px + max(36px, 4vh))", transform: "rotate(32deg)" }} />
      <Clip style={{ right: "26%", top: "9%", transform: "rotate(-58deg) scale(.9)" }} />
      <Clip style={{ right: "12%", bottom: "34%", transform: "rotate(12deg) scale(.8)" }} />

      <div className="op-prop op-polaroid" aria-hidden>
        <div className="op-polaroid__photo" />
        <div className="op-polaroid__cap">{caption}</div>
      </div>
    </>
  );
}

function Clip({ style }: { style: CSSProperties }) {
  return (
    <svg className="op-prop" style={{ width: 28, ...style }} viewBox="0 0 28 66" aria-hidden>
      <path
        d="M9 40 V12 a7 7 0 0 1 14 0 V50 a10 10 0 0 1 -20 0 V16"
        fill="none"
        stroke="#c4c9cf"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

// Desk lamp seen from above, with a bulb that sits inside the shade.
export function Lamp() {
  return (
    <svg className="op-lamp" viewBox="0 0 240 240" aria-hidden>
      <defs>
        <radialGradient id="op-shade" cx="42%" cy="42%" r="62%">
          <stop offset="0" stopColor="#fff0c4" />
          <stop offset=".32" stopColor="#e0a94a" />
          <stop offset=".7" stopColor="#3c5a49" />
          <stop offset="1" stopColor="#1d2f26" />
        </radialGradient>
        <radialGradient id="op-base" cx="40%" cy="40%" r="70%">
          <stop offset="0" stopColor="#d1a850" />
          <stop offset="1" stopColor="#6a4e1c" />
        </radialGradient>
      </defs>
      <circle cx="184" cy="188" r="38" fill="url(#op-base)" />
      <circle cx="184" cy="188" r="16" fill="#3b2a0e" opacity=".55" />
      <path d="M184 188 L132 112 L92 90" fill="none" stroke="#a98433" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="132" cy="112" r="8" fill="#d1a850" />
      <circle cx="84" cy="84" r="72" fill="url(#op-shade)" />
      <circle cx="84" cy="84" r="72" fill="none" stroke="#12201a" strokeWidth="3" />
      <circle cx="84" cy="84" r="30" fill="#fff4cf" opacity=".92" />
    </svg>
  );
}

// Slow drifting specks catching the lamp light. Skipped for reduced motion.
export function Dust() {
  const reduce = useReducedMotion();
  const specks = useMemo(
    () =>
      Array.from({ length: 34 }, (_, i) => {
        // deterministic pseudo-random so StrictMode renders match
        const r = (n: number) => {
          const s = Math.sin(i * 12.9898 + n * 78.233) * 43758.5453;
          return s - Math.floor(s);
        };
        return {
          left: `${6 + r(1) * 70}%`,
          top: `${10 + r(2) * 80}%`,
          size: 1.5 + r(3) * 2.5,
          dur: 11 + r(4) * 12,
          delay: -r(5) * 20,
          dx: -30 + r(6) * 60,
          o: 0.25 + r(7) * 0.5,
        };
      }),
    [],
  );
  if (reduce) return null;
  return (
    <motion.div aria-hidden initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.2, duration: 2 }} style={{ position: "absolute", inset: 0 }}>
      {specks.map((s, i) => (
        <span
          key={i}
          className="op-dust"
          style={
            {
              left: s.left,
              top: s.top,
              width: s.size,
              height: s.size,
              "--dur": `${s.dur}s`,
              "--delay": `${s.delay}s`,
              "--dx": `${s.dx}px`,
              "--o": s.o,
            } as CSSProperties
          }
        />
      ))}
    </motion.div>
  );
}
