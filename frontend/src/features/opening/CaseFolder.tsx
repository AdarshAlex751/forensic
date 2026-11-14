import { motion } from "framer-motion";

interface Props {
  caseId: string | null;
  title: string | null;
  open: boolean;
  reduce: boolean;
}

// Closed manila folder. The front cover swings open on its left edge to show the papers inside.
export function CaseFolder({ caseId, title, open, reduce }: Props) {
  return (
    <div className="op-folder">
      <div className="op-folder__back" />
      <motion.div
        className="op-sheet"
        style={{ rotate: -1.5 }}
        animate={{ y: open ? -10 : 0 }}
        transition={{ duration: reduce ? 0 : 0.7, delay: reduce ? 0 : 0.35, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="op-sheet__bars" aria-hidden>
          <i style={{ width: "62%" }} />
          <i />
          <i style={{ width: "86%" }} />
          <i style={{ width: "48%" }} />
        </div>
      </motion.div>
      <motion.div
        className="op-sheet"
        style={{ rotate: 1.2, top: "9%" }}
        animate={{ y: open ? -22 : 0 }}
        transition={{ duration: reduce ? 0 : 0.8, delay: reduce ? 0 : 0.45, ease: [0.22, 1, 0.36, 1] }}
      />
      <motion.div
        className="op-cover"
        animate={{ rotateY: open ? -168 : 0 }}
        transition={{ duration: reduce ? 0.01 : 1.0, ease: [0.65, 0, 0.35, 1] }}
      >
        <div className="op-face op-face--front">
          <div className="op-label">
            {caseId ? <p className="op-label__case">CASE {caseId}</p> : <p className="op-label__case">CASE</p>}
            {title ? <p className="op-label__title">{title}</p> : <span className="op-label__skeleton" aria-hidden />}
          </div>
        </div>
        <div className="op-face op-face--inside" />
      </motion.div>
    </div>
  );
}
