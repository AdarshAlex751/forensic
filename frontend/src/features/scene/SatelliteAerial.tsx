import { useEffect, useRef, useState } from "react";
import * as L from "leaflet";
import "leaflet/dist/leaflet.css";

// EOX 2016: CC BY 4.0. Public tiles require attribution and fair use, no API key.
const TILES="https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg";
export function SatelliteAerial({image,onFallback}:{image:string|null;onFallback:()=>void}) {
  const host=useRef<HTMLDivElement>(null);
  const mapRef=useRef<L.Map|null>(null);
  const overlayRef=useRef<L.ImageOverlay|null>(null);
  const boundsRef=useRef<L.LatLngBounds|null>(null);
  const [opacity,setOpacity]=useState(100);
  const [ready,setReady]=useState(false);
  const [error,setError]=useState("");
  const [tileError,setTileError]=useState(false);
  useEffect(()=>{
    const abort=new AbortController();
    let resize:ResizeObserver|undefined;
    fetch("/api/scene/aerial/bounds",{signal:abort.signal}).then(async r=>{
      if(!r.ok) throw new Error("Building coordinates could not load. Check the scene backend.");
      return r.json();
    }).then(location=>{
      if(abort.signal.aborted || !host.current) return;
      const {north,south,east,west}=location.bounds;
      if(![north,south,east,west,location.center.lat,location.center.lng].every(Number.isFinite)) throw new Error("Invalid aerial coordinates.");
      boundsRef.current=L.latLngBounds([south,west],[north,east]);
      const reduced=window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const map=L.map(host.current,{center:[location.center.lat,location.center.lng],zoom:17,minZoom:2,maxZoom:21,zoomAnimation:!reduced,fadeAnimation:!reduced});
      mapRef.current=map;
      L.tileLayer(TILES,{maxNativeZoom:14,maxZoom:21,attribution:'<a href="https://cloudless.eox.at">EOxCloudless</a> by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2016)'}).on("tileerror",()=>setTileError(true)).addTo(map);
      L.control.scale({imperial:false}).addTo(map);
      resize=new ResizeObserver(()=>{if(host.current?.offsetWidth) map.invalidateSize({pan:false});});
      resize.observe(host.current);
      setReady(true);
    }).catch(e=>{if(!abort.signal.aborted) setError(e instanceof Error?e.message:"Satellite map unavailable.");});
    return ()=>{abort.abort();resize?.disconnect();mapRef.current?.remove();mapRef.current=null;overlayRef.current=null;};
  },[]);
  useEffect(()=>{
    if(!ready || !image || !boundsRef.current || !mapRef.current) return;
    const overlay=L.imageOverlay(image,boundsRef.current,{opacity:1,attribution:"Imagery © Vexcel Imaging US, Inc."}).addTo(mapRef.current);
    overlayRef.current=overlay;
    return ()=>{overlay.remove();overlayRef.current=null;};
  },[ready,image]);
  useEffect(()=>{overlayRef.current?.setOpacity(opacity/100);},[opacity,ready,image]);
  return <div className="satellite-aerial">
    <div className="aerial-controls">
      <button disabled={!ready} onClick={()=>{if(boundsRef.current) mapRef.current?.fitBounds(boundsRef.current,{animate:false,padding:[24,24]});}}>Center building</button>
      <button disabled={!ready} onClick={()=>{if(boundsRef.current) mapRef.current?.setView(boundsRef.current.getCenter(),14,{animate:false});}}>Surroundings</button>
      <label>Vexcel detail <input aria-label="Vexcel overlay opacity" type="range" min="0" max="100" value={opacity} disabled={!image || !ready} onChange={e=>setOpacity(Number(e.target.value))}/></label>
      <button onClick={onFallback}>Image only</button>
    </div>
    {error ? <p role="alert">{error} Use Image only to continue.</p> : !ready && <p role="status">Loading satellite surroundings...</p>}
    {tileError && <p role="status">Some surrounding tiles could not load. The Vexcel building view is still available.</p>}
    <div ref={host} className="satellite-map" aria-label="Open satellite map with Vexcel building overlay"/>
    <p className="satellite-caption">Surroundings: 2016 Sentinel mosaic. Building detail: Vexcel. Imagery dates and resolution differ.</p>
  </div>;
}
