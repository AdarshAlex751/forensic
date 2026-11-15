import { useCallback, useEffect, useRef, useState } from "react";

/** A run of text with an optional style name (rendered as a class by the page). */
export interface Part {
  text: string;
  cls?: string;
}

/** One typed paragraph or line. Blocks are typed in order; the next starts when the previous finishes. */
export interface Block {
  id: string;
  cls: string;
  parts: Part[];
}

export const blockLength = (b: Block) => b.parts.reduce((n, p) => n + p.text.length, 0);
export const blockText = (b: Block) => b.parts.map((p) => p.text).join("");

/** Milliseconds before the next character: uneven (25-70 ms), longer after punctuation, longer still at breaks. */
export function delayAfter(ch: string): number {
  let ms = 25 + Math.random() * 45;
  if (ch === "." || ch === "!" || ch === "?") ms += 120 + Math.random() * 110;
  else if (ch === "," || ch === ";" || ch === ":") ms += 60 + Math.random() * 60;
  else if (ch === "\n") ms += 200 + Math.random() * 150;
  return ms;
}

/** The pause between one block and the next (a carriage return). */
export const BLOCK_PAUSE_MS = () => 320 + Math.random() * 280;

export interface Position {
  /** Index of the block being typed (== blocks.length when finished). */
  block: number;
  /** Characters of that block already typed. */
  chars: number;
}

interface Options {
  /** Show everything at once (already typed once, or the user prefers reduced motion). */
  instant: boolean;
  /** Typing restarts whenever this changes (e.g. the generation time of the questions). */
  resetKey: string;
  onFinish?: () => void;
}

/**
 * Types `blocks` one character at a time. State is only the position, so a render costs one block, not the letter:
 * the page memoises finished blocks. Returns the position, whether typing is over, and skip() to finish immediately.
 */
export function useTypewriter(blocks: Block[], { instant, resetKey, onFinish }: Options) {
  const end = (): Position => ({ block: blocks.length, chars: 0 });
  const [pos, setPos] = useState<Position>(() => (instant ? end() : { block: 0, chars: 0 }));
  const posRef = useRef(pos);
  const timer = useRef<number | undefined>(undefined);
  const blocksRef = useRef(blocks);
  const finish = useRef(onFinish);
  blocksRef.current = blocks;
  finish.current = onFinish;

  const set = useCallback((p: Position) => {
    posRef.current = p;
    setPos(p);
  }, []);

  const stop = () => {
    if (timer.current !== undefined) window.clearTimeout(timer.current);
    timer.current = undefined;
  };

  const skip = useCallback(() => {
    stop();
    const was = posRef.current.block >= blocksRef.current.length;
    set({ block: blocksRef.current.length, chars: 0 });
    if (!was) finish.current?.();
  }, [set]);

  useEffect(() => {
    stop();
    if (instant || blocks.length === 0) {
      set({ block: blocks.length, chars: 0 });
      return stop;
    }
    set({ block: 0, chars: 0 });
    const step = () => {
      const bs = blocksRef.current;
      const { block, chars } = posRef.current;
      if (block >= bs.length) return;
      const text = blockText(bs[block]);
      if (chars < text.length) {
        set({ block, chars: chars + 1 });
        timer.current = window.setTimeout(step, delayAfter(text[chars]));
      } else if (block + 1 < bs.length) {
        set({ block: block + 1, chars: 0 });
        timer.current = window.setTimeout(step, BLOCK_PAUSE_MS());
      } else {
        set({ block: bs.length, chars: 0 });
        finish.current?.();
      }
    };
    timer.current = window.setTimeout(step, 450);
    return stop;
    // blocks is read through a ref; typing restarts only when the key (or instant) changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey, instant]);

  return { pos, done: pos.block >= blocks.length, skip };
}
