import { useEffect, useMemo, useState } from "react";
import { useFindings } from "../../shared/useFindings";
import { useStore } from "../../shared/store";
import { AerialView } from "./AerialView";
import { GuidedMatterport } from "./GuidedMatterport";
import { walkthroughEntries } from "./timeline";
import "./timeline.css";

export function ScenePage() {
  const { data } = useFindings();
  const entries = useMemo(() => walkthroughEntries(data?.events || []), [data]);
  const [index,setIndex] = useState(0);
  const [inside,setInside] = useState(true);
  const [setup,setSetup] = useState(false);
  const selected = entries[Math.min(index,entries.length-1)];
  const setSelectedEventId = useStore(s=>s.setSelectedEventId);
  const setTimelineTime = useStore(s=>s.setTimelineTime);

  function select(i:number) {
    if (!entries[i]) return;
    setIndex(i);
    if (entries[i].room || entries[i].destination) setInside(true);
  }
  useEffect(() => {
    setSelectedEventId(selected?.source ? selected.id : null);
    setTimelineTime(selected?.t || null);
  },[selected?.id,selected?.source,setSelectedEventId,setTimelineTime]);
  return <div className="incident-scene">
    <header className="incident-header">
      <div><h1>The Titan Files</h1><p>Rabinowitz Hall / March 4, 2026 / EST (-05:00)</p></div>
      <button aria-pressed={setup} onClick={()=>{setInside(true);setSetup(!setup);}}>{setup ? "Return to timeline" : "Set up views"}</button>
    </header>
    <div className="incident-mode"><strong>{entries.length} of 15 key incidents</strong><p>Every stop links to a source record from the case data. Select a timestamp to explore.</p></div>
    <div className="incident-stage">
      <section className="combined-viewer" aria-label="Building viewer">
        <div className="viewer-switch" aria-label="Viewer mode">
          <button aria-pressed={inside} onClick={()=>setInside(true)}>Inside</button>
          <button aria-pressed={!inside} onClick={()=>{setInside(false);setSetup(false);}}>Aerial / roof</button>
        </div>
        <div hidden={!inside}><GuidedMatterport entry={selected} setup={setup}/></div>
        <div hidden={inside}><AerialView/></div>
      </section>
      <aside className="event-slip" aria-live="polite">
        {selected ? <><span className="event-step">Incident {index+1} of {entries.length}</span><span className="event-time">{selected.t.slice(11,19)} EST</span>
          <h2>{selected.title}</h2><span className={selected.room ? "room-badge" : "note-badge"}>{selected.room ? `Room ${selected.room}` : selected.destination === "reception" ? "Reception / opening view" : "Timeline note / view unchanged"}</span>
          <p className="event-summary">{selected.note?.summary || selected.detail}</p>
          {selected.note && <dl className="event-facts">{selected.note.facts.map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>}
          {selected.note?.context && <p className="event-context">{selected.note.context}</p>}
          {selected.source ? <details className="event-source"><summary>View original source</summary><p className="source-state">{selected.verified ? "Investigator verification complete" : "Source linked · investigator verification pending"}</p><dl className="event-facts"><div><dt>Source file</dt><dd>{selected.source.file}</dd></div><div><dt>Line</dt><dd>{selected.source.line}</dd></div></dl><h3>Original record</h3><pre>{selected.source.quote}</pre><h3>SHA-256</h3><code>{selected.source.sha256}</code></details> : <p className="preview-source">Scenario reference: CASE.md, incident-night timeline.</p>}
        </> : <><h2>Waiting for case evidence</h2><p>No matching source-backed incidents have loaded. Check the evidence connection.</p></>}
        {selected?.t.includes("18:16:40") && <p className="walk-note">Route comparison: 30 seconds between badge reads; configured walk time is 74 seconds.</p>}
      </aside>
    </div>
    <section className="incident-timeline" aria-label="Incident timeline">
      <div className="timeline-heading"><span>Incident timeline</span><small>Tap a timestamp / EST</small></div>
      <div className="event-markers" aria-label="Timestamp markers">{entries.map((event,i)=><button key={event.id} disabled={setup} aria-pressed={i===index} aria-label={`${event.t.slice(11,19)} ${event.title} ${event.room ? `Room ${event.room}` : event.destination === "reception" ? "Reception" : "Note"}`} onClick={()=>select(i)}>
        <time>{event.t.slice(11,19)}</time><span className="timeline-node" aria-hidden="true"/><span>{event.title}</span><small>{event.room ? `Room ${event.room}` : event.destination === "reception" ? "Reception" : "Note"}</small>
      </button>)}</div>
    </section>
  </div>;
}
