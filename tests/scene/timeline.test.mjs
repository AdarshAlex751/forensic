import assert from 'node:assert/strict';
import { walkthroughEntries, cameraRoom, evidenceEntries, previewEntries, estTime, indexAt } from '../../frontend/node_modules/.scene-tests/features/scene/timeline.js';

assert.equal(cameraRoom({room:'217',device:'rdr-217'}),'217');
assert.equal(cameraRoom({room:'219',device:'lt-219'}),'219');
assert.equal(cameraRoom({room:'corridor-219',device:'cam-03'}),'219');
assert.equal(cameraRoom({room:'230',device:'rdr-230'}),null);
assert.equal(cameraRoom({room:null,device:'wifi'}),null);
assert.equal(previewEntries.find(e=>e.t.includes('18:15:00')).room,null);
assert.equal(previewEntries.find(e=>e.t.includes('18:16:10')).room,null);
assert.ok(!previewEntries.some(e=>e.t.includes('18:44:00')));
assert.equal(estTime(Date.parse('2026-03-09T18:00:00-05:00')),'18:00:00');
const source={file:'access/badge_access.csv',line:1,quote:'badge OUT',sha256:'test'};
const base={id:'e1',type:'badge_out',t:'2026-03-04T18:02:00-05:00',person:'p_hank',device:'rdr-217',room:'217',source,verified:false};
assert.equal(evidenceEntries([base,{...base,id:'old',t:'2026-03-04T18:02:00-06:00'}]).length,1);
assert.equal(evidenceEntries([{...base,room:'parking',device:null,type:'parking_exit'}])[0].room,null);
assert.equal(indexAt(previewEntries,Date.parse('2026-03-04T18:15:10-05:00')),3);
console.log('Timeline checks passed: routing, note-only events, withheld parking, EST and legacy filtering.');

assert.equal(cameraRoom({room:'217',device:'ap-2-03'}),null);
assert.equal(evidenceEntries([{...base,person:null,device:'ap-2-03',type:'wifi_disassoc'}]).length,1);
assert.equal(previewEntries.find(e=>e.title==='Welcome reception').destination,'reception');

const fs=await import('node:fs');
const actual=JSON.parse(fs.readFileSync(new URL('../../data/evidence/events.json',import.meta.url),'utf8'));
const walk=walkthroughEntries(actual);
assert.equal(walk.length,15);
assert.equal(walk.filter(e=>e.source).length,15);
assert.ok(!walk.some(e=>e.title==='Welcome reception'));
assert.equal(walkthroughEntries([]).length,0);
assert.ok(walk.every(stop=>actual.some(e=>e.id===stop.id && e.t===stop.t && e.source.quote===stop.detail)));
assert.equal(walk.find(e=>e.title==='Wi-Fi disconnect').room,null);
assert.ok(!walk.some(e=>e.t.includes('18:44:00')));
console.log('15-stop walkthrough: 15 evidence matches, no scenario fallbacks.');

assert.ok(walk.every(e=>e.note?.summary && e.note.facts.length));
assert.ok(walk.find(e=>e.title==="Wi-Fi disconnect").note.context.includes("exact room"));
