// Person 1 builds this in hour 1 (Howler.js), then it is read-only. Skeleton stub: no-op.
export type SoundName = "pageTurn" | "typewriter" | "stamp" | "shutter" | "paperSlide";

let muted = false;
export const setMuted = (m: boolean) => {
  muted = m;
};
export const isMuted = () => muted;
export function play(_name: SoundName): void {
  /* placeholder */
}
