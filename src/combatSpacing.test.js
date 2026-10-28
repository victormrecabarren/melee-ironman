import {companionPosition,PARTNER_CONTACT_SEPARATION} from './previewCompanions.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {capsuleContact,matchupSpacing,GAME_UNIT} from './combatSpacing.js';
import {previewFrame,resultTiming} from './animationTimeline.js';
const m=JSON.parse(readFileSync(new URL('../public/melee-preview/manifest.json',import.meta.url)));

test('sphere/capsule contact respects radius, height and depth instead of adding bounding widths',()=>{
 const hit={center:[10,5,0],radius:2};
 assert.equal(capsuleContact(hit,{a:[3,5,0],b:[3,5,0],radius:1}).distance,16);
 assert.equal(capsuleContact(hit,{a:[3,8,0],b:[3,8,0],radius:1}).distance,13);
 assert.equal(capsuleContact(hit,{a:[3,9,0],b:[3,9,0],radius:1}),null);
 assert.equal(capsuleContact(hit,{a:[3,5,4],b:[3,5,4],radius:1}),null);
 assert.ok(Math.abs(capsuleContact(hit,{a:[3,0,0],b:[3,10,0],radius:1}).distance-16)<1e-6);
});

test('every installed matchup has a wider layout and a real active-frame contact for either winner',()=>{
 const entries=Object.entries(m.fighters),left=entries.filter(([,f])=>f.facing==='right'),right=entries.filter(([,f])=>f.facing==='left');
 for(const [a] of left)for(const [b] of right){
  const keys=[a,b],spacing=matchupSpacing(m,keys),gap=spacing.homes[1]-spacing.homes[0];
  assert.ok(gap>276);assert.equal(spacing.homes[0]+spacing.homes[1],1200);
  for(const winner of [0,1]){
   const c=spacing.contacts[winner];assert.ok(c,`${keys}: P${winner+1} geometry missing`);
   assert.ok(gap>c.distance*GAME_UNIT);
   const timing=resultTiming(m,winner,keys),state={mode:'result',winner,started:0,fighters:keys};
   assert.ok(m.fighters[keys[winner]].combatGeometry.hitFrames.some(f=>f.frame===timing.hits[0].frame));
   const f=previewFrame(state,(timing.hitAt+.001)*1000,m);
   const partner=timing.companionHits.length?companionPosition(f.positions[winner],winner,m):null;
   const contactFighter=partner || f.positions[winner];
   assert.ok(Math.abs(Math.abs(contactFighter.x-f.positions[1-winner].x)-c.distance*GAME_UNIT)<1e-6);
   if(partner)assert.ok(Math.abs(Math.abs(partner.x-f.positions[winner].x)-PARTNER_CONTACT_SEPARATION)<1e-6,'both hammers fit inside contact reach');
   assert.ok(f.positions[0].x<f.positions[1].x,'fighter roots must not pass through each other');
  }
 }
});

test('Falcon connects at extension, with no fixed 150px lunge added to his source animation',()=>{
 const keys=['captain-falcon','roy'],s=matchupSpacing(m,keys),t=resultTiming(m,0,keys),state={mode:'result',winner:0,started:0,fighters:keys};
 assert.ok(t.hits[0].frame>m.fighters[keys[0]].move.activeStart);
 assert.equal(previewFrame(state,m.fighters[keys[0]].move.activeStart/60*1000,m).impact,null);
 const f=previewFrame(state,t.hitAt*1000,m);assert.ok(f.impact);
 assert.ok(f.positions[0].x-s.homes[0]<80);
 assert.ok(f.positions[1].x-f.positions[0].x>400);
});

test('a replacement matchup repositions the survivor before the respawn transition',()=>{
 const state={mode:'result',winner:0,started:0,fighters:['dr-mario','roy'],nextFighters:['dr-mario','donkey-kong-left']};
 const t=resultTiming(m,0,state.fighters);
 const before=previewFrame(state,t.end*1000-.01,m),after=previewFrame(state,t.end*1000+.01,m);
 assert.ok(Math.abs(before.positions[0].x-after.positions[0].x)<.01);
 assert.ok(Math.abs(before.camera.zoom-after.camera.zoom)<1e-6);
});
