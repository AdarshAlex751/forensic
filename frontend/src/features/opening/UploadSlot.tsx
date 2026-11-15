import { useRef, useState } from "react";
import type { DragEvent } from "react";

interface Props {
  /** "empty": waiting for a file. "uploading": bytes are on their way (pct 0..100). */
  mode: "empty" | "uploading";
  filename?: string;
  pct?: number;
  onFile: (files: FileList) => void;
}

// The empty spot on the desk where the case folder will land once a zip is uploaded.
// A native <button> (Enter and Space open the picker for free) plus a hidden file input; also accepts a file dragged in.
export function UploadSlot({ mode, filename, pct = 0, onFile }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const depth = useRef(0); // dragenter/leave fire for every child; count them to avoid flicker

  const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
  const enter = (e: DragEvent) => {
    if (mode !== "empty" || !hasFiles(e)) return;
    e.preventDefault();
    depth.current += 1;
    setOver(true);
  };
  const leave = () => {
    depth.current = Math.max(0, depth.current - 1);
    if (depth.current === 0) setOver(false);
  };
  const dragOver = (e: DragEvent) => {
    if (mode === "empty" && hasFiles(e)) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    }
  };
  const drop = (e: DragEvent) => {
    e.preventDefault();
    depth.current = 0;
    setOver(false);
    if (mode === "empty" && e.dataTransfer.files.length) onFile(e.dataTransfer.files);
  };
  const choose = () => input.current?.click();
  const uploading = mode === "uploading";
  const checking = uploading && pct >= 100; // bytes are up; the server is unpacking and checking the zip

  return (
    <div
      className={`op-slot__spot${over ? " op-slot__spot--over" : ""}${uploading ? " op-slot__spot--busy" : ""}`}
      onDragEnter={enter}
      onDragOver={dragOver}
      onDragLeave={leave}
      onDrop={drop}
    >
      <input
        ref={input}
        className="op-file"
        type="file"
        accept=".zip,application/zip"
        tabIndex={-1}
        aria-hidden
        onChange={(e) => {
          if (e.target.files?.length) onFile(e.target.files);
          e.target.value = ""; // so choosing the same file again still fires
        }}
      />

      {uploading ? (
        <div className="op-slot__body" role="status" aria-live="polite">
          <p className="op-slot__title">{checking ? "Checking the case files…" : "Uploading…"}</p>
          {filename ? <p className="op-slot__file">{filename}</p> : null}
          <div
            className={`op-bar${checking ? " op-bar--wait" : ""}`}
            role="progressbar"
            aria-label="Upload progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={pct}
          >
            <i style={{ width: `${pct}%` }} />
          </div>
          <p className="op-slot__sub">{checking ? "Almost there" : `${pct}%`}</p>
        </div>
      ) : (
        <button type="button" className="op-slot__btn" onClick={choose} aria-label="Upload case file. Click or drop a .zip from your computer.">
          <svg className="op-slot__icon" viewBox="0 0 64 64" aria-hidden>
            <path d="M32 40V12M20 24l12-12 12 12" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M10 38v10a4 4 0 0 0 4 4h36a4 4 0 0 0 4-4V38" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className="op-slot__title">{over ? "Drop to upload" : "Upload case file"}</span>
          <span className="op-slot__sub">Click or drop a .zip from your computer</span>
        </button>
      )}
    </div>
  );
}
