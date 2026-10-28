import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {companionPosition,fighterAssetKeys,NANA_INPUT_DELAY} from './previewCompanions.js';
import {previewFrame,resultTiming} from './animationTimeline.js';
import {readyCamera,project,MOBILE_VIEW,FIGHTER_SCALE} from './previewCamera.js';
const manifest=JSON.parse(readFileSync(new URL('../public/melee-preview/manifest.json',import.meta.url)));
for(const side of [0,1]) test(`Ice Climbers side ${side}: both real models survive every preview phase`,()=>{
  const keys=side===0?['ice-climbers','roy-left']:['dr-mario','ice-climbers-left'];
  const nana=side===0?'nana':'nana-left';
  assert.ok(fighterAssetKeys(keys).includes(nana));
  assert.notEqual(manifest.fighters[nana].clips.idle.file,manifest.fighters[keys[side]].clips.idle.file);
  const timing=resultTiming(manifest,1-side,keys);
  for(const [mode,time] of [['entrance',0],['entrance',1250],['entrance',1600],['entrance',3000],['result',(timing.hitAt+.01)*1000],['result',(timing.koAt+.01)*1000],['result',(timing.end+.01)*1000]]) {
    const frame=previewFrame({mode,started:0,winner:1-side,fighters:keys},time,manifest);
    const p=frame.positions[side],partner=companionPosition(p,side,manifest);
    assert.equal(partner.fighter,nana);assert.equal(partner.y,p.y);assert.equal(partner.alpha,p.alpha);
    assert.ok(manifest.fighters[nana].clips[partner.clip]);
    assert.equal(Math.sign(partner.x-p.x),side===0?-1:1);
  }
  const p={fighter:keys[side],x:500,y:456,clip:'smash',time:0,alpha:1};
  assert.equal(companionPosition(p,side,manifest).clip,'idle');
  assert.equal(companionPosition({...p,time:1},side,manifest).time,1-NANA_INPUT_DELAY);
  const frame=previewFrame({mode:'entrance',started:0,fighters:keys},3000,manifest);
  const camera=readyCamera(MOBILE_VIEW,manifest,keys);
  const partner=companionPosition(frame.positions[side],side,manifest), f=manifest.fighters[nana],scale=FIGHTER_SCALE*f.scale;
  for(const x of [f.readyBounds[0],f.readyBounds[2]]) {
    const point=project(camera,partner.x+(x-f.anchor[0])*scale,partner.y,MOBILE_VIEW);
    assert.ok(point.x>=40 && point.x<=MOBILE_VIEW.width-40);
  }
});
test('single fighters require no companion images',()=>{
 assert.deepEqual(fighterAssetKeys(['falco','roy-left']),['falco','roy-left']);
 assert.equal(companionPosition({fighter:'falco'},0,manifest),null);
});
for(const winner of [0,1]) test(`paired smash P${winner+1}: independent hitstop, two source bursts, launch after Nana`,()=>{
 const fighters=winner===0?['ice-climbers','sheik-left']:['sheik','ice-climbers-left'];
 const state={mode:'result',started:0,winner,fighters};
 const timing=resultTiming(manifest,winner,fighters),[first,second]=timing.hits;
 assert.equal(timing.hits.length,2);
 assert.ok(Math.abs(second.at-first.at-6/60)<1e-8);
 const at=t=>previewFrame(state,t*1000,manifest);
 const a=at(first.at+.5/60),b=at(first.at+3.5/60);
 assert.equal(a.positions[winner].time,b.positions[winner].time,'Popo freezes on his own hit');
 assert.ok(companionPosition(b.positions[winner],winner,manifest).time>companionPosition(a.positions[winner],winner,manifest).time,'Nana keeps swinging during Popo hitstop');
 assert.equal(b.impacts.length,1);
 const c=at(second.at+.5/60),d=at(second.at+3.5/60);
 assert.equal(c.impacts.length,2);
 assert.ok(c.impacts[0].age>c.impacts[1].age,'first burst continues while the second begins');
 assert.equal(companionPosition(c.positions[winner],winner,manifest).time,companionPosition(d.positions[winner],winner,manifest).time,'Nana freezes on her own hit');
 assert.ok(d.positions[winner].time>c.positions[winner].time,'Popo recovers independently');
 const victim=1-winner;
 assert.equal(c.positions[victim].x,d.positions[victim].x,'victim remains held through second hit');
 assert.notEqual(at(second.at+second.hitlag+1/60).positions[victim].x,d.positions[victim].x);
});
