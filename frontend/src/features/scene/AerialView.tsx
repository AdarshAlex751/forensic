import { useEffect, useRef, useState } from "react";


export function AerialView() {
  const [zoom,setZoom] = useState(1);
  const [offset,setOffset] = useState({x:0,y:0});
  const drag = useRef<{id:number;x:number;y:number} | null>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const reset = () => {setZoom(1);setOffset({x:0,y:0});};
  const changeZoom = (delta:number) => setZoom(old=>Math.max(1,Math.min(5,old+delta)));
  useEffect(()=>{
    if (zoom === 1) setOffset({x:0,y:0});
  },[zoom]);
  const [image, setImage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | undefined;
    setImage(null);
    setError(null);
    fetch("/api/scene/aerial", { signal: controller.signal }).then(async (response) => {
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : "Aerial imagery is currently unavailable.");
      }
      const blob = await response.blob();
      if (!blob.type.startsWith("image/")) throw new Error("The aerial service did not return an image. Please retry.");
      if (controller.signal.aborted) return;
      objectUrl = URL.createObjectURL(blob);
      setImage(objectUrl);
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "Aerial imagery is currently unavailable.");
    });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [attempt]);

  return <figure className="aerial-view" aria-label="Building aerial view">
    <h2>Roof & surroundings</h2>
    <div>
    <div className="aerial-controls" aria-label="Aerial navigation">
      <button disabled={!image || zoom>=5} onClick={()=>changeZoom(.5)} aria-label="Zoom in aerial">+</button>
      <output aria-live="polite">{Math.round(zoom*100)}%</output>
      <button disabled={!image || zoom<=1} onClick={()=>changeZoom(-.5)} aria-label="Zoom out aerial">−</button>
      <button disabled={!image} onClick={reset}>Reset view</button>
      <span>Zoom, then drag to explore. Arrow keys pan; + and − zoom.</span>
    </div>
    <div className="aerial-image interactive-aerial" ref={viewport} tabIndex={0} role="region" aria-label="Interactive roof imagery"
      onKeyDown={e=>{
        if (["+","=","-","ArrowLeft","ArrowRight","ArrowUp","ArrowDown","Home"].includes(e.key)) e.preventDefault();
        if (e.key==="+" || e.key==="=") changeZoom(.5);
        if (e.key==="-") changeZoom(-.5);
        if (e.key==="Home") reset();
        if (zoom>1 && e.key.startsWith("Arrow")) setOffset(o=>({x:Math.max(-500,Math.min(500,o.x+(e.key==="ArrowLeft"?40:e.key==="ArrowRight"?-40:0))),y:Math.max(-500,Math.min(500,o.y+(e.key==="ArrowUp"?40:e.key==="ArrowDown"?-40:0)))}));
      }}
      onPointerDown={e=>{if (!image || zoom<=1 || e.button!==0) return; e.currentTarget.setPointerCapture(e.pointerId);drag.current={id:e.pointerId,x:e.clientX,y:e.clientY};}}
      onPointerMove={e=>{const d=drag.current;if (!d || d.id!==e.pointerId) return;const dx=e.clientX-d.x,dy=e.clientY-d.y;drag.current={id:d.id,x:e.clientX,y:e.clientY};setOffset(o=>({x:Math.max(-500,Math.min(500,o.x+dx)),y:Math.max(-500,Math.min(500,o.y+dy))}));}}
      onPointerUp={()=>{drag.current=null;}} onPointerCancel={()=>{drag.current=null;}} onLostPointerCapture={()=>{drag.current=null;}}>

    {image ? <img draggable={false} style={{transform:`translate(${offset.x}px, ${offset.y}px) scale(${zoom})`}} src={image} alt="Vexcel aerial imagery centered on the selected Matterport model's coordinates"
      onError={()=>{setImage(null);setError("The aerial image could not be displayed. Please retry.");}} /> :
      <p role={error ? "alert" : "status"}>{error || "Loading Vexcel aerial imagery..."}</p>}
    {error && <button type="button" className="mt-2 underline" onClick={() => setAttempt((value) => value + 1)}>Retry aerial image</button>}
    </div>
    </div>
    <figcaption className="mt-2 text-sm">
      Imagery © Vexcel Imaging US, Inc. The view uses the model's map coordinates;
      entrances and camera locations have not yet been mapped.
    </figcaption>
  </figure>;
}
