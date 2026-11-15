import { useEffect, useRef, useState } from "react";
import { setupSdk, type MpSdk } from "@matterport/sdk";
import type { EventRec, Contradiction, Device } from "../../shared/types";

const MODEL_ID = import.meta.env.VITE_MATTERPORT_MODEL_ID?.trim() || "P3S6VUTP3qB";
const SDK_KEY = import.meta.env.VITE_MATTERPORT_SDK_KEY?.trim();
const MODEL_URL = `https://my.matterport.com/show/?m=${MODEL_ID}`;

/** User-selected location preview; evidence-to-sweep mapping is still pending. */
export function MatterportScene({ selectedEvent, selectedContradiction, devices = [] }: {
  selectedEvent?: EventRec; selectedContradiction?: Contradiction; devices?: Device[];
}) {
  const container = useRef<HTMLDivElement>(null);
  const [sdk, setSdk] = useState<MpSdk | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState("Loading building tour...");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sweeps, setSweeps] = useState<MpSdk.Sweep.ObservableSweepData[]>([]);
  const [currentSweep, setCurrentSweep] = useState("");
  const [room, setRoom] = useState("219");
  const [mappingMessage, setMappingMessage] = useState("");
  const [roomMappings, setRoomMappings] = useState<Record<string, string>>({});

  useEffect(() => {
    fetch("/api/scene/config").then((r) => r.json()).then((config) => {
      const entries = (config.rooms || []).filter((r: { sweep?: string }) => r.sweep)
        .map((r: { id: string; sweep: string }) => [r.id, r.sweep]);
      setRoomMappings(Object.fromEntries(entries));
    }).catch(() => setMappingMessage("Room mapping could not be loaded."));
  }, []);

  useEffect(() => {
    if (!sdk || !selectedEvent?.room) return;
    const destination = roomMappings[selectedEvent.room];
    if (!destination || !sweeps.some((s) => s.id === destination)) return;
    void sdk.Sweep.moveTo(destination, {
      transition: sdk.Sweep.Transition.INSTANT,
    }).catch(() => setError("The selected event's mapped scan position is unavailable."));
  }, [sdk, selectedEvent?.id, roomMappings, sweeps]);

  useEffect(() => {
    if (!sdk || !sweeps.length) return;
    let cancelled = false;
    let ids: string[] = [];
    const descriptors = devices.flatMap((device) => {
      const sweep = sweeps.find((s) => s.id === roomMappings[device.room]);
      if (!sweep) return [];
      return [{ label: `${device.id} / room ${device.room}`,
        description: "Case device marker at the manually assigned room position; exact device placement is pending.",
        anchorPosition: sweep.position, stemVector: { x: 0, y: .4, z: 0 },
        color: device.id === selectedEvent?.device ? { r: 1, g: .2, b: .2 } : { r: .3, g: .65, b: 1 } }];
    });
    if (descriptors.length) void sdk.Tag.add(...descriptors).then((added) => {
      ids = added;
      if (cancelled) void sdk.Tag.remove(...ids).catch(() => {});
    }).catch(() => { if (!cancelled) setError("Case markers could not be displayed."); });
    return () => { cancelled = true; if (ids.length) void sdk.Tag.remove(...ids).catch(() => {}); };
  }, [sdk, devices, roomMappings, sweeps, selectedEvent?.device]);

  async function saveMapping() {
    const sweep = sweeps.find((s) => s.id === currentSweep);
    if (!sweep) return;
    setMappingMessage("Saving room position...");
    try {
      const response = await fetch("/api/scene/mapping", { method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: MODEL_ID, room_id: room, sweep, sweeps }) });
      if (!response.ok) throw new Error();
      setRoomMappings((old) => ({ ...old, [room]: sweep.id }));
      setMappingMessage(`Room ${room} assigned to this scan position.`);
    } catch { setMappingMessage("Room position could not be saved. Check the scene backend."); }
  }

  useEffect(() => {
    const host = container.current;
    if (!host) return;
    let disposed = false;
    let connection: MpSdk | undefined;
    const subscriptions: { cancel(): void }[] = [];
    const iframe = document.createElement("iframe");
    iframe.title = "Princeton Rabinowitz Hall foyer - Matterport tour";
    iframe.className = "h-full w-full border-0";
    iframe.allow = "fullscreen; xr-spatial-tracking; autoplay";
    iframe.allowFullscreen = true;
    const url = new URL(MODEL_URL);
    url.searchParams.set("play", "1");
    if (SDK_KEY) url.searchParams.set("applicationKey", SDK_KEY);
    iframe.src = url.toString();
    host.appendChild(iframe);
    setSdk(null);
    setSweeps([]);
    setCurrentSweep("");
    setError(null);
    setStatus(SDK_KEY ? "Connecting to building tour..." : "Tour preview; scene controls are not configured.");

    const timer = window.setTimeout(() => {
      if (!disposed && SDK_KEY) setError("The tour is taking longer than expected. You can retry or open it in a new tab.");
    }, 30_000);

    if (SDK_KEY) {
      setupSdk(SDK_KEY, { iframe, space: MODEL_ID }).then(async (connected) => {
        if (disposed) { connected.disconnect(); return; }
        connection = connected;
        const model = await connected.Model.getData();
        if (disposed) return;
        if (model.sid !== MODEL_ID) throw new Error("Unexpected model");
        subscriptions.push(connected.Sweep.data.subscribe({
          onCollectionUpdated(collection) {
            if (!disposed) setSweeps(Object.values(collection));
          },
        }));
        subscriptions.push(connected.Sweep.current.subscribe((sweep) => {
          if (!disposed) setCurrentSweep(sweep.id || "");
        }));
        window.clearTimeout(timer);
        setSdk(connected);
        setStatus("Building tour connected");
        setError(null);
      }).catch(() => {
        if (disposed) return;
        window.clearTimeout(timer);
        setError("Scene controls could not connect. Open the app on localhost and check the SDK key's allowed domains and model access.");
        setStatus("Tour controls unavailable");
      });
    }

    return () => {
      disposed = true;
      window.clearTimeout(timer);
      subscriptions.forEach((subscription) => subscription.cancel());
      connection?.disconnect();
      iframe.remove();
    };
  }, [attempt]);

  async function changeView(view: "INSIDE" | "DOLLHOUSE" | "FLOORPLAN") {
    if (!sdk || busy) return;
    setBusy(true);
    setError(null);
    try {
      await sdk.Mode.moveTo(sdk.Mode.Mode[view], {
        transition: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? sdk.Mode.TransitionType.INSTANT : sdk.Mode.TransitionType.FLY,
      });
    } catch {
      setError("This view is unavailable for the current scan. Try another view.");
    } finally {
      setBusy(false);
    }
  }

  function exportSweeps() {
    const payload = {
      model_id: MODEL_ID,
      source: "Matterport Showcase SDK Sweep.data",
      captured_at: new Date(Date.now() - 5 * 3600000).toISOString().replace("Z", "-05:00"),
      coordinate_system: "Matterport SDK, meters, Y up",
      sweeps,
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${MODEL_ID}-sweeps.json`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <figure className="mt-4">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        {(["INSIDE", "DOLLHOUSE", "FLOORPLAN"] as const).map((view) => (
          <button key={view} type="button" disabled={!sdk || busy}
            className="rounded border px-3 py-1 disabled:opacity-40"
            onClick={() => void changeView(view)}>
            {{ INSIDE: "Walk through", DOLLHOUSE: "Dollhouse", FLOORPLAN: "Floor plan" }[view]}
          </button>
        ))}
        <span role="status" className="text-sm">{status}</span>
      </div>
      {error && <div role="alert" className="mb-3 text-sm">
        {error}{" "}
        <button type="button" className="underline" onClick={() => setAttempt((value) => value + 1)}>Retry tour</button>
      </div>}
      <div ref={container} className="aspect-video min-h-80 w-full overflow-hidden rounded border border-current/20" />
      <figcaption className="mt-2 text-sm">
        Princeton Rabinowitz Hall foyer.{' '}
        <a className="underline" href={MODEL_URL} target="_blank" rel="noreferrer">
          Open tour in a new tab
        </a>
        <p className="mt-2">
          Location preview: demo rooms, devices, and travel times have not yet
          been mapped to this scan.
        </p>
        <details className="mt-3">
          <summary>Scene mapping setup</summary>
          <p>{sweeps.length} scan positions received. Current position: {currentSweep || "not inside a scan position"}.</p>
          <p>Navigate to a room entrance, confirm its number on the floor plan, then assign the current position.</p>
          <label>Room <select value={room} onChange={(event) => setRoom(event.target.value)} className="bg-stone-800">
            {Array.from({length: 21}, (_, i) => String(210 + i)).map((id) => <option key={id}>{id}</option>)}
          </select></label>{" "}
          <button type="button" disabled={!sdk || !currentSweep} onClick={() => void saveMapping()} className="underline disabled:opacity-40">Assign current position</button>
          <p role="status">{mappingMessage}</p>
          <button type="button" className="mt-2 underline disabled:opacity-40"
            disabled={!sdk || sweeps.length === 0} onClick={exportSweeps}>
            Export scan positions and connections
          </button>
        </details>
        {selectedContradiction?.kind === "physical" && <p className="mt-3">
          Selected route: {selectedContradiction.path?.join(" → ") || "Awaiting mapped route"}.
          {" "}Event gap: {selectedContradiction.gap_s ?? "unknown"} s.
          {" "}A route through the scan requires confirmed room mappings.
        </p>}
      </figcaption>
    </figure>
  );
}
