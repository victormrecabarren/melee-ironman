import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {initialLineup,takeStock,lineupFighters,withPlayedCharacters} from './previewRoster.js';
import {capturePreviewSession,parsePreviewSession,restorePreviewPlayback,readPreviewSession,writePreviewSession,PREVIEW_SESSION_KEY} from './previewSession.js';
import {previewFrame,resultTiming,releasePlatform} from './animationTimeline.js';
const manifest=JSON.parse(readFileSync(new URL('../public/melee-preview/manifest.json',import.meta.url)));
const storage=()=>{const values=new Map();return {getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)};};
test('early drop survives a reload without restarting the platform wait',()=>{
 const state={mode:'entrance',started:1000,fighters:lineupFighters(initialLineup()),stocks:[2,2],matchStart:true};
 const released=releasePlatform(state,1200);
 const saved=parsePreviewSession(JSON.stringify(snapshot({playback:released,now:1400})));
 const restored=restorePreviewPlayback(saved,80000);
 assert.deepEqual(previewFrame(restored,80000,manifest),previewFrame(released,1400,manifest));
 for(const invalid of [-1,1.06,null,'0.2']) {
  assert.throws(()=>parsePreviewSession(JSON.stringify({...saved,playback:{...saved.playback,platformHoldSeconds:invalid}})));
 }
});
function snapshot(overrides={}) {
 const lineup=initialLineup();
 return capturePreviewSession({lineup,pending:null,history:[],playback:{mode:'entrance',started:1000,fighters:lineupFighters(lineup),stocks:[2,2],idleSince:[500,1000]},now:5000,playedSounds:new Set(['land-0']),sound:false,reduced:false,...overrides});
}
test('reload restores the same fighters, stock totals, stats, preferences, and undo history',()=>{
 const before=initialLineup(),lineup=takeStock(takeStock(before,0),1);
 const store=storage(),s=snapshot({lineup,history:[before,takeStock(before,0)],playback:{mode:'entrance',started:1000,fighters:lineupFighters(lineup),stocks:[1,1]}});
 assert.equal(writePreviewSession(s,store),'');
 const loaded=readPreviewSession(store).session;
 assert.deepEqual(loaded.lineup,lineup);assert.deepEqual(loaded.history[0],before);
 assert.equal(loaded.sound,false);assert.deepEqual(loaded.playedSounds,['land-0']);
 const frame=previewFrame(restorePreviewPlayback(loaded,90000),90000,manifest);
 assert.equal(frame.ready,true);assert.deepEqual(frame.stocks,[1,1]);
});
test('pending KO survives reload once, without dropping or double-counting the accepted stock',()=>{
 for(const elapsed of [0,1500]) {
  const lineup=initialLineup(),pending=takeStock(lineup,0),fighters=lineupFighters(lineup);
  const p={mode:'result',winner:0,started:1000,fighters,stocks:[2,2],nextFighters:lineupFighters(pending),nextStocks:[2,1],finishedRun:false};
  const s=parsePreviewSession(JSON.stringify(snapshot({lineup,pending,history:[lineup],playback:p,now:1000+elapsed})));
  const restored=restorePreviewPlayback(s,80000);
  assert.deepEqual(s.pending.stockHistory,[{side:0,character:'dr-mario',victim:'roy'}]);
  const result=previewFrame(restored,80000+resultTiming(manifest,0).end*1000,manifest);
  assert.deepEqual(result.stocks,[2,1]);assert.equal(s.pending.stockHistory.length,1);
 }
});
test('relative idle and animation clocks survive a new browser time origin',()=>{
 const s=snapshot();const restored=restorePreviewPlayback(s,60000);
 assert.equal(60000-restored.started,4000);
 assert.deepEqual(restored.idleSince,[55500,56000]);
});
test('fresh arrival status survives reload separately from ordinary revival',()=>{
 for(const fresh of [false,true]){
  const playback={mode:'respawn',winner:0,started:1000,fighters:['dr-mario','marth-left'],stocks:[2,fresh?2:1],arrivals:[false,fresh]};
  const s=parsePreviewSession(JSON.stringify(snapshot({playback,now:1200})));
  const frame=previewFrame(restorePreviewPlayback(s,80000),80000,manifest);
  assert.equal(frame.platforms[0].kind,fresh?'arrival':'revival');
  assert.equal(frame.effects.some(e=>e.kind==='arrival-glow'),fresh);
 }
 const invalid=snapshot();invalid.playback.arrivals=[false,'yes'];
 assert.throws(()=>parsePreviewSession(JSON.stringify(invalid)));
});
test('finished match restores Game! without restarting the roster',()=>{
 let before=initialLineup();for(let i=0;i<51;i++)before=withPlayedCharacters(takeStock(before,0));
 const final=takeStock(before,0),fighters=lineupFighters(before);
 const p={mode:'result',winner:0,started:1000,fighters,stocks:before.players.map(p=>p.stocks),finishedRun:true};
 const s=parsePreviewSession(JSON.stringify(snapshot({lineup:final,playback:p,now:9000,history:[before]})));
 const frame=previewFrame(restorePreviewPlayback(s,50000),50000,manifest);
 assert.equal(frame.complete,true);assert.equal(frame.next,undefined);
 assert.equal(frame.stocks[1],0);assert.equal(s.lineup.stockHistory.length,52);
});
test('corrupt saves and unavailable storage report failure without crashing',()=>{
 const store=storage();store.setItem(PREVIEW_SESSION_KEY,'{broken');
 assert.equal(readPreviewSession(store).session,null);assert.ok(readPreviewSession(store).error);
 for(const modify of [s=>s.lineup.players[0].index=999,s=>s.playback.fighters[0]='unknown',s=>s.elapsed=-1]) {
  const s=snapshot();modify(s);assert.throws(()=>parsePreviewSession(JSON.stringify(s)));
 }
 const blocked={getItem(){throw new Error('blocked')},setItem(){throw new Error('quota')}};
 assert.ok(readPreviewSession(blocked).error);assert.ok(writePreviewSession(snapshot(),blocked));
 assert.equal(readPreviewSession(storage()).error,'');
});
test('Start Over replaces a finished saved run with fresh characters, stocks, stats and undo',async()=>{
 const {freshPreviewSession}=await import('./previewSession.js');
 const store=storage();let lineup=initialLineup();for(let i=0;i<52;i++)lineup=takeStock(lineup,0);
 writePreviewSession(snapshot({lineup,history:[initialLineup()]}),store);
 const fresh=freshPreviewSession(true);
 assert.equal(writePreviewSession(fresh,store),'');
 const loaded=readPreviewSession(store).session;
 assert.deepEqual(loaded.lineup,initialLineup());assert.deepEqual(loaded.history,[]);
 assert.equal(loaded.pending,null);assert.deepEqual(loaded.playedSounds,[]);
 assert.equal(loaded.sound,true);assert.equal(loaded.reduced,true);
 assert.deepEqual(loaded.playback.fighters,['dr-mario','roy-left']);
 assert.deepEqual(loaded.playback.stocks,[2,2]);assert.equal(loaded.playback.mode,'entrance');
 assert.equal(loaded.elapsed,0);
});
