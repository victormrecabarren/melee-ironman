import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {chargeProgress} from './smashInteraction.js';
import {previewFrame,resultTiming,FIGHTERS} from './animationTimeline.js';
import {capturePreviewSession,parsePreviewSession,restorePreviewPlayback} from './previewSession.js';
import {initialLineup} from './previewRoster.js';
const manifest=JSON.parse(fs.readFileSync(new URL('../public/melee-preview/manifest.json',import.meta.url)));
const state={mode:'charge',winner:0,started:0,fighters:FIGHTERS,stocks:[2,2]};
test('every facing has the original charge command and taunt with bounded sprite pages',()=>{
 for(const fighter of Object.values(manifest.fighters)) {
  assert.equal(fighter.move.charge.frames,60);
  assert.ok(['Appeal','AppealL','AppealR'].includes(fighter.clips.taunt.source));
  assert.equal(fighter.clips.taunt.clippedFrames.length,0);
  for(const p of fighter.clips.taunt.pages)assert.ok(p.width<=2048 && p.height<=2048);
 }
});
test('tap continues the windup; holding freezes the original charge frame and caps at 60 frames',()=>{
 const c=manifest.fighters[FIGHTERS[0]].move.charge,at=c.frame*1000/60;
 const tap=chargeProgress(state,20,manifest);assert.equal(tap.sourceTime,.02);assert.equal(tap.frames,0);
 const hold=chargeProgress(state,at+500,manifest);assert.equal(hold.sourceTime,c.frame/60);assert.equal(hold.frames,30);assert.equal(hold.complete,false);
 assert.equal(chargeProgress(state,at+1000,manifest).complete,true);
 assert.equal(chargeProgress(state,at+5000,manifest).frames,60);
 const f=previewFrame(state,at+500,manifest);
 assert.equal(f.ready,false);assert.deepEqual(f.stocks,[2,2]);assert.equal(f.ko,null);assert.equal(f.next,undefined);
 assert.ok(f.effects.some(e=>e.kind==='charge-dust'));assert.ok(f.positions[0].overlay);
 assert.ok(!f.effects.some(e=>e.kind==='smash-flash'),'initial flash ages while bones hold');
 const released=previewFrame({...state,mode:'result',chargeFrames:30},at,manifest);
 assert.ok(!released.effects.some(e=>e.kind==='smash-flash'),'release does not restart the windup flash');
});
test('charging applies source damage multiplier and hitlag; Link follow-up resets the charge',()=>{
 const plain=resultTiming(manifest,0),charged=resultTiming(manifest,0,FIGHTERS,60);
 assert.ok(charged.hits[0].hitbox.Damage>plain.hits[0].hitbox.Damage);
 assert.ok(charged.hitlag>=plain.hitlag);
 for(const key of ['link','young-link']) {
  const fighters=[key,'roy-left'],base=resultTiming(manifest,0,fighters),full=resultTiming(manifest,0,fighters,60);
  assert.ok(full.hits[0].hitbox.Damage>base.hits[0].hitbox.Damage);
  assert.equal(full.hits[1].hitbox.Damage,base.hits[1].hitbox.Damage);
 }
});
test('abandoned holds persist as ready without awarding a stock; charged results retain their clock',()=>{
 const lineup=initialLineup();
 const saved=capturePreviewSession({lineup,pending:null,history:[],playback:state,now:700,playedSounds:[],sound:true,reduced:false});
 const s=parsePreviewSession(JSON.stringify(saved));assert.equal(s.playback.mode,'entrance');assert.deepEqual(s.lineup,lineup);
 assert.equal(previewFrame(restorePreviewPlayback(s,8000),8000,manifest).ready,true);
 for(const chargeFrames of [-1,61,NaN,1.5])assert.throws(()=>parsePreviewSession(JSON.stringify({...saved,playback:{...saved.playback,chargeFrames}})));
});
test('last-stock taunt follows the finished smash without delaying respawn',()=>{
 for(const winner of [0,1]) {
  const t=resultTiming(manifest,winner,FIGHTERS,0,true);
  const result={mode:'result',winner,started:0,fighters:FIGHTERS,stocks:[1,1],celebrate:true};
  assert.equal(previewFrame(result,(t.tauntAt-.01)*1000,manifest).positions[winner].clip,'smash');
  assert.equal(previewFrame(result,(t.tauntAt+.1)*1000,manifest).positions[winner].clip,'taunt');
  assert.equal(t.end,resultTiming(manifest,winner,FIGHTERS,0,false).end);
  assert.equal(previewFrame({...result,celebrate:false},(t.tauntAt+.1)*1000,manifest).positions[winner].clip,'idle');
  const final={...result,finishedRun:true};
  const f=previewFrame(final,(Math.max(t.koAt,t.tauntAt)+.1)*1000,manifest);
  assert.equal(f.complete,true);assert.equal(f.next,undefined);assert.equal(f.positions[winner].clip,'taunt');
 }
});
test('long taunts overlap the next fighter platform and drop without delaying ready',()=>{
 for(const winner of [0,1]) {
  const fighters=winner===0?['young-link','roy-left']:['roy','young-link-left'];
  const nextFighters=winner===0?['young-link','marth-left']:['marth','young-link-left'];
  const timing=resultTiming(manifest,winner,fighters,0,true);
  const result={mode:'result',winner,started:1000,fighters,stocks:[1,1],nextFighters,nextStocks:[2,2],celebrate:true};
  const transition=1000+timing.end*1000;
  const first=previewFrame(result,transition,manifest),next=first.next;
  assert.equal(next.mode,'respawn');assert.equal(first.platforms.length,1);
  assert.equal(first.positions[winner].clip,'taunt');
  assert.deepEqual(first.stocks,[2,2]);assert.deepEqual(next.fighters,nextFighters);
  const readyAt=1.55+manifest.fighters[nextFighters[1-winner]].clips.landing.duration+.01;
  for(const elapsed of [0,1.2,readyAt]) {
   const now=transition+elapsed*1000,frame=previewFrame(next,now,manifest);
   const age=(now-1000)/1000-timing.tauntAt,duration=manifest.fighters[fighters[winner]].clips.taunt.duration;
   assert.equal(frame.positions[winner].clip,age<duration?'taunt':'idle');
   assert.ok(Math.abs(frame.positions[winner].time-(age<duration?age:age-duration))<1e-6);
   assert.equal(frame.positions[1-winner].clip,elapsed===0?'idle':elapsed===1.2?'fall':'idle');
   if(elapsed===readyAt)assert.equal(frame.ready,true,'long taunt must not block the next matchup');
  }
  const now=transition+1200;
  const saved=parsePreviewSession(JSON.stringify(capturePreviewSession({lineup:initialLineup(),pending:null,
   history:[],playback:next,now,playedSounds:['taunt-0'],sound:true,reduced:false})));
  const restored=previewFrame(restorePreviewPlayback(saved,90000),90000,manifest);
  const original=previewFrame(next,now,manifest);
  for(const side of [0,1]) {
   assert.equal(restored.positions[side].clip,original.positions[side].clip);
   for(const field of ['time','x','y'])assert.ok(Math.abs(restored.positions[side][field]-original.positions[side][field])<1e-6);
  }
  assert.deepEqual(saved.playedSounds,['taunt-0']);
  assert.throws(()=>parsePreviewSession(JSON.stringify({...saved,playback:{...saved.playback,tauntStarted:null}})));
  const finished=previewFrame(next,1000+(timing.tauntEnd+.1)*1000,manifest);
  assert.equal(finished.positions[winner].clip,'idle');assert.ok(Math.abs(finished.positions[winner].time-.1)<1e-6);
  const reduced=previewFrame(result,1601,manifest,true);
  assert.equal(reduced.next.tauntStarted,undefined);assert.equal(reduced.positions[winner].clip,'idle');
 }
});
