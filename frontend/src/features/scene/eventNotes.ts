import type { EventRec } from "../../shared/types";

type ParsedEvent = EventRec & {actor?:{kind:string;value:string}|null;attrs?:Record<string,unknown>};
export function eventNote(event:EventRec) {
  const row=event as ParsedEvent;
  const attrs=row.attrs || {};
  const actor=row.actor?.value || "Unidentified";
  const device=event.device || "Not recorded";
  const room=event.room || "Not recorded";
  const text=(key:string)=>typeof attrs[key]==="string"?String(attrs[key]):"Not recorded";
  const facts:[string,string][]=[];
  let summary="", context="";
  if(event.type.startsWith("badge_")) {
    summary=`Badge ${actor} recorded an ${event.type==='badge_in'?'entry':'exit'} at room ${room}.`;
    facts.push(["Badge",actor],["Reader",device],["Access result",text("result")]);
    context="A badge read identifies the credential used, not necessarily the person carrying it.";
  } else if(event.type.startsWith("camera_")) {
    summary=event.type==='camera_offline'?`${device} went offline outside room 219.`:`The recorded offline interval for ${device} ended.`;
    facts.push(["Camera",device],["Status",event.type==='camera_offline'?"Offline":"Offline interval ended"]);
    context="This stop represents the camera status log. No security-camera footage is shown.";
  } else if(event.type==='logon' || event.type==='logoff') {
    summary=`The account ${actor} ${event.type==='logon'?'logged on to':'logged off'} laptop ${device}.`;
    facts.push(["Account",actor],["Laptop",device]);
    context="The record identifies an account session; it does not independently identify the operator.";
  } else if(event.type==='usb_mount') {
    summary=`A USB storage device was connected to laptop ${device}.`;
    facts.push(["Device",[attrs.vendor,attrs.product].filter(Boolean).join(' ') || "USB storage"],["Serial number",text("serial")]);
  } else if(event.type==='file_read' || event.type==='file_copy') {
    summary=`The account ${actor} ${event.type==='file_copy'?'copied':'read'} a Titan project file on ${device}.`;
    facts.push(["Account",actor],["File",text("path")]);
    if(event.type==='file_copy') facts.push(["Destination volume",text("target_volume")]);
    if(typeof attrs.bytes==='number') facts.push(["File size",`${attrs.bytes.toLocaleString('en-US')} bytes`]);
  } else if(event.type==='wifi_disassoc') {
    summary=`The device with MAC address ${actor} disconnected from access point ${device}.`;
    facts.push(["MAC address",actor],["Access point",device],["Network",text("ssid")]);
    context="An access point connection does not establish the device's exact room. The camera view stays unchanged.";
  } else if(event.type==='maintenance_window') {
    summary=`Maintenance was scheduled for ${device}, assigned to ${text("technician")}.`;
    facts.push(["Work order",text("work_order")],["Scheduled window",`${text("start").slice(11,19)}–${text("end").slice(11,19)} EST`]);
    context="A scheduled work order is not proof that the work was completed.";
  } else summary=event.type.replaceAll('_',' ');
  return {summary,facts,context};
}
