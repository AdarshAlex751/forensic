import { AnimatePresence, animate, motion, useMotionValue, useReducedMotion, useSpring, useTransform } from "framer-motion";
import type { MotionValue } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { play } from "../../shared/sounds";
import { CaseFolder } from "./CaseFolder";
import { Dust, DeskProps, Lamp } from "./DeskProps";
import { UploadSlot } from "./UploadSlot";
import { ZIP_MESSAGE, isZip, uploadCase } from "./uploadCase";
import type { Upload } from "./uploadCase";
import "./opening.css";

type Phase = "idle" | "moving" | "opening" | "pushing" | "leaving";
// The folder does not exist until a case zip is uploaded. Its label comes from the upload reply, never from the
// cached findings (which still describe the previous case).
type Source = { kind: "empty" } | { kind: "uploading"; name: string; pct: number } | { kind: "ready"; caseId: string; filename: string };

// Hoisted so framer sees the same keyframe arrays on every render (no accidental re-animation).
const DROP_IN = { opacity: 1, y: [-90, 0, -7, 0], rotate: [5, 0, -0.8, 0] };
const DROP_TIMING = { duration: 0.95, times: [0, 0.5, 0.75, 1], ease: "easeOut" as const };

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const EASE = [0.65, 0, 0.35, 1] as const;

// Full-screen fixed layer: covers the shared header on purpose. Route "/".
export function OpeningScreen() {
  const reduce = useReducedMotion() ?? false;

  const [source, setSource] = useState<Source>({ kind: "empty" });
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [settled, setSettled] = useState(false); // after the first reveal, the slot comes back quickly
  const upload = useRef<Upload | null>(null);
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
    // A file dropped beside the slot must not make the browser navigate to it and leave the app.
    const stopFileDrop = (e: DragEvent) => {
      if (Array.from(e.dataTransfer?.types ?? []).includes("Files")) e.preventDefault();
    };
    window.addEventListener("dragover", stopFileDrop);
    window.addEventListener("drop", stopFileDrop);
    const t = window.setTimeout(() => setSettled(true), 2600);
    return () => {
      alive.current = false;
      upload.current?.abort();
      window.clearTimeout(t);
      document.body.style.overflow = prev;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("dragover", stopFileDrop);
      window.removeEventListener("drop", stopFileDrop);
    };
  }, [mx, my, reduce]);

  function pickFiles(files: FileList) {
    if (source.kind !== "empty") return;
    setUploadError(null);
    if (files.length > 1) return setUploadError("Choose one .zip file at a time.");
    const file = files[0];
    if (!file || !isZip(file)) return setUploadError(ZIP_MESSAGE);

    setSource({ kind: "uploading", name: file.name, pct: 0 });
    const u = uploadCase(file, (pct) => {
      if (alive.current) setSource((s) => (s.kind === "uploading" ? { ...s, pct } : s));
    });
    upload.current = u;
    u.done
      .then((r) => {
        if (!alive.current) return;
        setSource({ kind: "ready", caseId: r.case_id, filename: r.filename });
        play("paperSlide");
      })
      .catch((e: Error) => {
        if (!alive.current) return;
        setSource({ kind: "empty" }); // never stay stuck in "Uploading…"
        setUploadError(e.message);
      })
      .finally(() => {
        if (upload.current === u) upload.current = null;
      });
  }

  function chooseAnother() {
    if (phase !== "idle") return;
    fx.set(0);
    fy.set(0);
    setHot(false);
    setUploadError(null);
    setSource({ kind: "empty" }); // local only: nothing is sent to the backend
  }

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
    if (phase !== "idle" || source.kind !== "ready" || !zoneRef.current || !folderRef.current) return;
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
    // A full page load, not navigate(): useFindings caches the old case, and the new upload must be read fresh.
    // We do not wait for the backend pipeline to finish.
    if (alive.current) window.location.assign("/summary");
  }

  const ready = source.kind === "ready";
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
            <DeskProps caption={source.kind === "ready" ? `Case ${source.caseId}` : ""} />
          </motion.div>
        </Layer>

        <Layer depth={8} mx={mx} my={my} className="op-layer--stage">
          <div className="op-stage">
            <div className="op-row">
              <motion.div
                ref={zoneRef}
                className={`op-zone${hot ? " op-zone--hot" : ""}${ready ? "" : " op-zone--waiting"}`}
                animate={{ opacity: isOpen ? 0 : 1 }}
                {...(isOpen ? {} : intro(1.0))}
              >
                <span className="op-zone__text">Drop the case folder here</span>
              </motion.div>

              <div className="op-slotcol">
                <div className="op-slot">
                  <AnimatePresence>
                    {!ready && (
                      <motion.div
                        key="slot"
                        className="op-slot__fill"
                        {...(reduce
                          ? {}
                          : settled
                            ? { initial: { opacity: 0 }, animate: { opacity: 1 }, transition: { duration: 0.35 } }
                            : intro(1.25))}
                        exit={{ opacity: 0, transition: { duration: reduce ? 0 : 0.35 } }}
                      >
                        <UploadSlot
                          mode={source.kind === "uploading" ? "uploading" : "empty"}
                          filename={source.kind === "uploading" ? source.name : undefined}
                          pct={source.kind === "uploading" ? source.pct : 0}
                          onFile={pickFiles}
                        />
                      </motion.div>
                    )}
                    {source.kind === "ready" && (
                      <motion.div
                        key="folder"
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
                        initial={reduce ? { opacity: 0 } : { opacity: 0, y: -90, rotate: 5 }}
                        animate={reduce ? { opacity: 1, y: 0 } : DROP_IN}
                        transition={reduce ? { duration: 0.2 } : DROP_TIMING}
                        exit={{ opacity: 0, y: 24, transition: { duration: reduce ? 0 : 0.3 } }}
                      >
                        <CaseFolder caseId={source.caseId} title={source.filename} open={isOpen} reduce={reduce} />
                      </motion.div>
                    )}
                  </AnimatePresence>
                  {ready && !reduce && !busy ? <span key={source.caseId + source.filename} className="op-thud" aria-hidden /> : null}
                </div>

                <div className="op-under">
                  {uploadError && !ready ? (
                    <p className="op-upload-error" role="alert">
                      {uploadError}
                    </p>
                  ) : null}
                  {ready && !busy ? (
                    <button type="button" className="op-link" onClick={chooseAnother}>
                      Upload a different file
                    </button>
                  ) : null}
                </div>
              </div>
            </div>

            <motion.div className="op-footer" animate={{ opacity: busy ? 0 : 1 }} {...(busy ? {} : intro(1.8))}>
              <p className="op-hint">
                {ready ? "Drag the folder onto the marked spot, or open it with the button." : "Upload a case file and its folder appears on the desk."}
              </p>
              <button type="button" className="op-button" onClick={() => void openCase()} disabled={busy || !ready}>
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
