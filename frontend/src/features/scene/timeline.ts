import { eventNote } from "./eventNotes.js";
import type { EventRec } from "../../shared/types";

export type SceneRoom = "217" | "219";
export interface TimelineEntry {
  id: string; t: string; title: string; detail: string; room: SceneRoom | null;
  destination?: "reception";
  note?: ReturnType<typeof eventNote>;
  source?: EventRec["source"]; verified?: boolean;
}
export function cameraRoom(event: Pick<EventRec, "room" | "device">): SceneRoom | null {
  if (event.device?.startsWith("ap-")) return null;
  if (event.device === "cam-03") return "219";
  return event.room === "217" || event.room === "219" ? event.room : null;
}
export function evidenceEntries(events: EventRec[]): TimelineEntry[] {
  return events.filter(e => e.t.startsWith("2026-03-04T") && e.t.endsWith("-05:00") &&
    (e.person?.startsWith("p_") || /^(rdr-2[12][0-9]|rdr-230|lt-219|cam-0[1-6]|ap-2-0[1-7])$/.test(e.device || "")))
    .map(e => ({id:e.id, t:e.t, title:e.type.replaceAll("_", " "), detail:e.source.quote,
      room:cameraRoom(e), source:e.source, verified:e.verified}))
    .sort((a,b) => Date.parse(a.t) - Date.parse(b.t));
}
// Authoring preview from CASE.md section 5. These are story beats, never evidence.
// Parking remains absent until the evidence slice releases its record.
const beats: [string, string, string, SceneRoom | null][] = [
  ["17:45:00", "Maggie badges out", "Maggie's badge records an OUT at room 217.", "217"],
  ["18:02:00", "Hank badges out", "Hank's badge records an OUT at room 217.", "217"],
  ["18:05:00", "Camera offline", "cam-03 goes offline. Show room 219, not a security-camera perspective.", "219"],
  ["18:15:00", "Welcome reception", "The summit welcome reception starts. Return to the opening building view.", null],
  ["18:16:10", "Badge read at room 230", "The technician's badge number is read at room 230. Timeline note only.", null],
  ["18:16:40", "Badge read at room 219", "The same badge number is read at 219, 30 seconds later. Configured walking time: 74 seconds. A badge read does not identify who carried it.", "219"],
  ["18:17:05", "Local account logon", "Account hgibson logs onto the isolated laptop lt-219.", "219"],
  ["18:17:30", "USB mounted", "A USB mass-storage device mounts on lt-219.", "219"],
  ["18:17:30", "Titan file activity", "Between 18:17 and 18:31, account hgibson reads and copies Titan files. This marker represents the interval, not an exact first-copy time.", "219"],
  ["18:30:00", "Camera online", "cam-03 returns online. The view remains at room 219.", "219"],
  ["18:31:20", "Account logoff", "Account hgibson logs off lt-219.", "219"],
  ["18:31:40", "Badge out of room 219", "The technician's badge number records an OUT at 219.", "219"],
  ["18:41:00", "Wi-Fi disconnect", "Hank's laptop disconnects from floor Wi-Fi. This does not establish an exact room.", null],
  ["19:00:00", "Scheduled maintenance", "Frederik's maintenance window in room 219 runs from 19:00 to 21:30.", "219"],
];
export const previewEntries: TimelineEntry[] = beats.map(([time,title,detail,room],i) => ({
  id:`preview-${i}`,t:`2026-03-04T${time}-05:00`,title,detail,room,destination: title === "Welcome reception" ? "reception" : undefined,
}));
export function estTime(epoch: number): string {
  return new Date(epoch - 5 * 3600000).toISOString().slice(11,19);
}
export function indexAt(entries: TimelineEntry[], time: number): number {
  let index = 0;
  entries.forEach((entry,i) => { if (Date.parse(entry.t) <= time) index = i; });
  return index;
}

// Deliberate walkthrough selection: never turn every raw record into a stop.
export function walkthroughEntries(events: EventRec[]): TimelineEntry[] {
  const stops = previewEntries.map(entry => ({...entry}));
  stops[8] = {...stops[8], t:"2026-03-04T18:17:58-05:00", title:"Titan files read", detail:"The first recorded Titan file read in the incident sequence."};
  stops.splice(9,0,{id:"walkthrough-copy",t:"2026-03-04T18:18:02-05:00",title:"Titan files copied",detail:"The first recorded file copy; further copy records continue until 18:29:33.",room:"219"});
  const kinds = ["badge_out","badge_out","camera_offline",null,"badge_in","badge_in","logon","usb_mount","file_read","file_copy","camera_online","logoff","badge_out","wifi_disassoc","maintenance_window"];
  const devices = ["rdr-217","rdr-217","cam-03",null,"rdr-230","rdr-219","lt-219","lt-219","lt-219","lt-219","cam-03","lt-219","rdr-219","ap-2-03","lt-219"];
  // Replace the unsourced reception with the last recorded copy in this sequence.
  stops.splice(10,0,{id:"walkthrough-last-copy",t:"2026-03-04T18:29:33-05:00",title:"Last recorded Titan copy",detail:"",room:"219"});
  kinds.splice(10,0,"file_copy"); devices.splice(10,0,"lt-219");
  return stops.flatMap((stop,i): TimelineEntry[]=>{
    if (!kinds[i]) return [];
    const record=events.find(event=>event.t===stop.t && event.type===kinds[i] && event.device===devices[i]);
    if (!record?.source?.file || !record.source.line || !record.source.quote || !record.source.sha256) return [];
    return [{...stop,id:record.id,t:record.t,detail:record.source.quote,note:eventNote(record),room:cameraRoom(record),source:record.source,verified:record.verified}];
  });
}
