import { animate, motion, useMotionValue, useReducedMotion, useSpring, useTransform } from "framer-motion";
import type { MotionValue } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { play } from "../../shared/sounds";
import { useFindings } from "../../shared/useFindings";
import { CaseFolder } from "./CaseFolder";
import { Dust, DeskProps, Lamp } from "./DeskProps";
import "./opening.css";

type Phase = "idle" | "moving" | "opening" | "pushing" | "leaving";

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const EASE = [0.65, 0, 0.35, 1] as const;

// Full-screen fixed layer: covers the shared header on purpose. Route "/".
export function OpeningScreen() {
  const navigate = useNavigate();
  const reduce = useReducedMotion() ?? false;
  const { data, error } = useFindings();

  const [phase, setPhase] = useState<Phase>("idle");
  const [hot, setHot] = useState(false);
  const [origin, setOrigin] = useState("50% 50%");

  const zoneRef = useRef<HTMLDivElement>(null);
  const folderRef = useRef<HTMLDivElement>(null);
  const alive = useRef(true);
  const fx = useMotionValue(0);
  const fy = useMotionValue(0);

  // Mouse parallax: normalised -0.5..0.5, smoothed by springs.
  const mx = useSpring(useMotionValue(0), { stiffness: 60, damping: 18 });
  const my = useSpring(useMotionValue(0), { stiffness: 60, damping: 18 });

  useEffect(() => {
    alive.current = true;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onMove = (e: PointerEvent) => {
      if (reduce) return;
      mx.set(e.clientX / window.innerWidth - 0.5);
      my.set(e.clientY / window.innerHeight - 0.5);
    };
    window.addEventListener("pointermove", onMove);
    return () => {
      alive.current = false;
      document.body.style.overflow = prev;
      window.removeEventListener("pointermove", onMove);
    };
  }, [mx, my, reduce]);

  const center = (el: HTMLElement) => {
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  };

  const overZone = () => {
    if (!zoneRef.current || !folderRef.current) return false;
    const z = zoneRef.current.getBoundingClientRect();
    const f = center(folderRef.current);
    return f.x > z.left && f.x < z.right && f.y > z.top && f.y < z.bottom;
  };

  async function openCase() {
    if (phase !== "idle" || !zoneRef.current || !folderRef.current) return;
    const k = reduce ? 0 : 1;
    setHot(false);
    setPhase("moving");

    // slide the folder onto the drop spot
    const z = center(zoneRef.current);
    const f = center(folderRef.current);
    const tx = fx.get() + (z.x - f.x);
    const ty = fy.get() + (z.y - f.y);
    setOrigin(`${z.x}px ${z.y}px`);
    await Promise.all([
      animate(fx, tx, { duration: 0.6 * k, ease: EASE }),
      animate(fy, ty, { duration: 0.6 * k, ease: EASE }),
    ]);
    if (!alive.current) return;

    setPhase("opening");
    play("paperSlide");
    await sleep(1150 * k);
    if (!alive.current) return;

    setPhase("pushing"); // camera push-in
    await sleep(1000 * k);
    if (!alive.current) return;

    setPhase("leaving"); // fade to black, then go
    await sleep(450 * k);
    if (alive.current) navigate("/summary");
  }

  const busy = phase !== "idle";
  const isOpen = phase === "opening" || phase === "pushing" || phase === "leaving";
  const pushed = phase === "pushing" || phase === "leaving";
  const intro = (delay: number, y = 14) =>
    reduce ? {} : { initial: { opacity: 0, y }, animate: { opacity: 1, y: 0 }, transition: { delay, duration: 0.9, ease: [0.22, 1, 0.36, 1] as const } };

  return (
    <div className="op-root" role="region" aria-label="Case opening screen">
      <motion.div
        className="op-scene"
        style={{ transformOrigin: origin }}
        animate={{ scale: pushed && !reduce ? 2.7 : 1 }}
        transition={{ duration: 1.05, ease: EASE }}
      >
        <Layer depth={6} mx={mx} my={my} className="op-wood" />

        {/* lamp glow with an occasional flicker */}
        <Layer depth={10} mx={mx} my={my}>
          <motion.div
            className="op-light"
            style={{ position: "absolute", inset: 0 }}
            initial={reduce ? false : { opacity: 0 }}
            animate={
              reduce
                ? { opacity: 1 }
                : { opacity: [0, 1, 1, 0.72, 1, 0.86, 0.97, 1, 1] }
            }
            transition={
              reduce
                ? undefined
                : { duration: 11, times: [0, 0.06, 0.5, 0.52, 0.54, 0.56, 0.6, 0.62, 1], repeat: Infinity, repeatDelay: 0, ease: "linear" }
            }
          />
        </Layer>

        <Layer depth={18} mx={mx} my={my}>
          <motion.div style={{ position: "absolute", inset: 0 }} {...intro(0.5, 0)}>
            <DeskProps caption={data?.case.address ?? ""} />
          </motion.div>
        </Layer>

        <Layer depth={8} mx={mx} my={my} className="op-layer--stage">
          <div className="op-stage">
            <div className="op-row">
              <motion.div
                ref={zoneRef}
                className={`op-zone${hot ? " op-zone--hot" : ""}`}
                animate={{ opacity: isOpen ? 0 : 1 }}
                {...(isOpen ? {} : intro(1.0))}
              >
                <span className="op-zone__text">Drop the case folder here</span>
              </motion.div>

              <motion.div
                ref={folderRef}
                className="op-folder-wrap"
                style={{ x: fx, y: fy }}
                drag={!busy}
                dragMomentum={false}
                dragSnapToOrigin
                dragElastic={0.12}
                whileDrag={{ scale: 1.05, rotate: -2 }}
                onDrag={() => setHot(overZone())}
                onDragEnd={() => {
                  if (overZone()) void openCase();
                  else setHot(false);
                }}
                {...(reduce
                  ? {}
                  : { initial: { opacity: 0, y: -40, rotate: 4 }, animate: { opacity: 1, y: 0, rotate: 0 }, transition: { delay: 1.25, duration: 1.0, ease: [0.22, 1, 0.36, 1] as const } })}
              >
                <CaseFolder caseId={data?.case.id ?? null} title={data?.case.title ?? null} open={isOpen} reduce={reduce} />
              </motion.div>
            </div>

            <motion.div className="op-footer" animate={{ opacity: busy ? 0 : 1 }} {...(busy ? {} : intro(1.8))}>
              <p className="op-hint">Drag the folder onto the marked spot, or open it with the button.</p>
              {error ? <p className="op-error">Couldn’t load the case data. Start the backend and reload this page.</p> : null}
              <button type="button" className="op-button" onClick={() => void openCase()} disabled={busy}>
                Open case folder
              </button>
            </motion.div>
          </div>
        </Layer>

        <Layer depth={30} mx={mx} my={my}>
          <motion.div style={{ position: "absolute", inset: 0 }} {...intro(0.15, 0)}>
            <Lamp />
          </motion.div>
        </Layer>
        <Layer depth={34} mx={mx} my={my}>
          <Dust />
        </Layer>

        <div className="op-vignette" />
      </motion.div>

      <motion.div className="op-fade" initial={false} animate={{ opacity: phase === "leaving" ? 1 : 0 }} transition={{ duration: reduce ? 0 : 0.45, ease: "easeIn" }} />
    </div>
  );
}

function Layer({ depth, mx, my, className, children }: { depth: number; mx: MotionValue<number>; my: MotionValue<number>; className?: string; children?: ReactNode }) {
  const x = useTransform(mx, (v) => -v * depth * 2);
  const y = useTransform(my, (v) => -v * depth * 2);
  return (
    <motion.div className={`op-layer ${className ?? ""}`} style={{ x, y }}>
      {children}
    </motion.div>
  );
}
