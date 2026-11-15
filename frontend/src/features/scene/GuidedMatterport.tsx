import { useEffect, useRef, useState } from "react";
import { setupSdk, type MpSdk } from "@matterport/sdk";
import type { SceneRoom, TimelineEntry } from "./timeline";

const MODEL = import.meta.env.VITE_MATTERPORT_MODEL_ID?.trim() || "P3S6VUTP3qB";
const KEY = import.meta.env.VITE_MATTERPORT_SDK_KEY?.trim();
type SavedView = { sweep: string; rotation?: { x: number; y: number } };
type Views = Partial<Record<SceneRoom, SavedView>>;

export function GuidedMatterport({ entry, setup }: {entry?: TimelineEntry; setup: boolean}) {
  const host = useRef<HTMLDivElement>(null);
  const pose = useRef<{x:number;y:number}>({x:0,y:0});
  const current = useRef<MpSdk.Sweep.ObservableSweepData | null>(null);
  const [openingView,setOpeningView] = useState<SavedView | null>(null);
  const [sdk,setSdk] = useState<MpSdk | null>(null);
  const [sweeps,setSweeps] = useState<MpSdk.Sweep.ObservableSweepData[]>([]);
  const [views,setViews] = useState<Views>({});
  const [room,setRoom] = useState<SceneRoom>("217");
  const [status,setStatus] = useState("Connecting to the building…");
  const [error,setError] = useState("");
  const [attempt,setAttempt] = useState(0);
  const [saving,setSaving] = useState(false);
  const [currentId,setCurrentId] = useState("");
  const wanted = useRef<TimelineEntry | undefined>(entry);
  wanted.current = entry;

  useEffect(() => {
    const abort = new AbortController();
    fetch("/api/scene/config",{signal:abort.signal}).then(async r => {
      if (!r.ok) throw new Error();
      const config = await r.json();
      const next: Views = {};
      for (const row of config.rooms || []) if (["217","219"].includes(row.id) && row.sweep)
        next[row.id as SceneRoom] = {sweep:row.sweep,rotation:row.view_rotation};
      setViews(next);
    }).catch(() => { if (!abort.signal.aborted) setError("Saved views could not load. Check the backend, then retry."); });
    return () => abort.abort();
  }, [attempt]);

  useEffect(() => {
    if (!host.current) return;
    let disposed = false;
    let initialSweep = "";
    let initialRotation: SavedView["rotation"];
    let captured = false;
    const captureOpening = () => {
      if (!disposed && !captured && initialSweep && initialRotation) {
        captured = true;
        setOpeningView({sweep:initialSweep,rotation:{...initialRotation}});
      }
    };
    setOpeningView(null);
    let connection: MpSdk | undefined;
    const subscriptions: {cancel():void}[] = [];
    const iframe = document.createElement("iframe");
    iframe.title = "Rabinowitz Hall guided incident view";
    iframe.allow = "autoplay; xr-spatial-tracking";
    iframe.tabIndex = 0;
    const url = new URL("https://my.matterport.com/show/");
    url.searchParams.set("m",MODEL); url.searchParams.set("play","1");
    if (KEY) url.searchParams.set("applicationKey",KEY);
    iframe.src = url.toString(); host.current.appendChild(iframe);
    setSdk(null); setStatus("Connecting to the building…");
    const timer = window.setTimeout(() => {if (!disposed) setError("The tour is taking longer than expected. Retry the connection.");},30000);
    if (KEY) void setupSdk(KEY,{iframe}).then(async connectionValue => {
      if (disposed) {connectionValue.disconnect();return;}
      connection = connectionValue;
      const model = await connection.Model.getData();
      if (disposed) return;
      if (model.sid !== MODEL) throw new Error();
      subscriptions.push(connection.Sweep.data.subscribe({onCollectionUpdated(collection) {
        if (!disposed) setSweeps(Object.values(collection));
      }}));
      subscriptions.push(connection.Sweep.current.subscribe(sweep => {
        current.current = sweep;
        if (sweep.id) {initialSweep = sweep.id;captureOpening();}
        if (!disposed) setCurrentId(sweep.id || "");
      }));
      subscriptions.push(connection.Camera.pose.subscribe(value => {pose.current = {x:value.rotation.x,y:value.rotation.y};initialRotation = pose.current;captureOpening();}));
      window.clearTimeout(timer); setSdk(connection); setStatus("Tour connected");
    }).catch(() => {if (!disposed) {window.clearTimeout(timer);setError("Tour connection failed. Use localhost and check SDK access.");}});
    else {window.clearTimeout(timer);setError("The Matterport SDK key is missing from local configuration.");}
    return () => {disposed=true;window.clearTimeout(timer);subscriptions.forEach(s=>s.cancel());connection?.disconnect();iframe.remove();};
  },[attempt]);

  // Sequential moves prevent an older camera request finishing after a newer selection.
  const moveChain = useRef<Promise<unknown>>(Promise.resolve());
  useEffect(() => {
    if (!sdk || !openingView || setup || !entry || (!entry.room && !entry.destination)) return;
    const selected = entry;
    const label = entry.destination === "reception" ? "Welcome reception" : `Room ${entry.room}`;
    const view = entry.destination === "reception" ? openingView : entry.room ? views[entry.room] : undefined;
    if (!view) {setStatus(`Room ${entry.room} view needs to be saved in Set up views.`);return;}
    let cancelled = false;
    moveChain.current = moveChain.current.catch(()=>{}).then(async () => {
      if (cancelled || wanted.current?.id !== selected.id) return;
      try {
        await sdk.Sweep.moveTo(view.sweep,{rotation:view.rotation,transition:sdk.Sweep.Transition.INSTANT});
        if (!cancelled) {setError("");setStatus(label);}
      } catch {if (!cancelled) setError(`${label} could not be opened. Retry the connection.`);}
    });
    return () => {cancelled=true;};
  },[sdk,entry?.id,setup,views,openingView]);

  async function saveView() {
    if (!current.current?.id || saving) return;
    setSaving(true);setError("");
    const saved = {sweep:current.current.id,rotation:{...pose.current}};
    try {
      const response = await fetch("/api/scene/mapping",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({model_id:MODEL,room_id:room,sweep:current.current,sweeps,view_rotation:saved.rotation})});
      if (!response.ok) throw new Error();
      setViews(old=>({...old,[room]:saved}));setStatus(`Saved room ${room}, including viewing direction.`);
    } catch {setError("View could not be saved. Check the backend and choose an enabled scan position.");}
    finally {setSaving(false);}
  }

  return <section className="guided-tour" aria-label="Matterport scene">
    <div className="tour-status"><span role="status">{!setup && !entry?.room && !entry?.destination ? "Timeline note / view unchanged" : status}</span>
      <span>{setup ? "View setup" : "Navigation unlocked"}</span></div>
    {error && <div role="alert" className="tour-error">{error} <button onClick={()=>{setError("");setAttempt(a=>a+1);}}>Retry</button></div>}
    <div className="tour-frame" ref={host} />
    {!setup && (!views["217"] || !views["219"]) && <p className="tour-hint">Save the two camera views in <strong>Set up views</strong> to enable room jumps. The timeline is ready to use.</p>}
    {setup && <div className="view-setup">
      <p>Navigate to the desired position and face the doorway or room. Save once for each room.</p>
      <label>Save as <select value={room} onChange={e=>setRoom(e.target.value as SceneRoom)}><option>217</option><option>219</option></select></label>
      <button disabled={!sdk || !currentId || saving} onClick={()=>void saveView()}>{saving ? "Saving…" : `Save room ${room} view`}</button>
      <p>217: {views["217"] ? "saved" : "not set"} · 219: {views["219"] ? "saved" : "not set"}</p>
    </div>}
  </section>;
}
