import { fighterScale } from './fighterScale.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { GAME_UNIT, stageScale, launchPosition, project, VIEW, MOBILE_VIEW, readyCamera, fighterTarget } from './previewCamera.js';
import { previewFrame, resultTiming } from './animationTimeline.js';
import { matchupHomes } from './combatSpacing.js';
const manifest = JSON.parse(readFileSync(new URL('../public/melee-preview/manifest.json', import.meta.url)));
const HOME=matchupHomes(manifest);

test('stage and fighters use the same disc-unit pixel density', () => {
  const projection = manifest.stageInfo.projection;
  const density = manifest.environment.stage.width / projection.stageOrthoWidth * projection.gameUnitMeters;
  assert.ok(Math.abs(density * stageScale(manifest) - GAME_UNIT) < 1e-9);
  assert.deepEqual(manifest.stageInfo.blastBounds, { left:-246, right:246, bottom:-140, top:188 });
});

test('entrance holds one camera from platform through landing', () => {
  const state = { mode:'entrance', started:0 };
  const opening = previewFrame(state, 0, manifest);
  const settled = previewFrame(state, 2500, manifest);
  assert.deepEqual(opening.camera, settled.camera);
  assert.equal(previewFrame(state, 1200, manifest).ready, false);
  assert.equal(settled.ready, true);
  const result = previewFrame({ mode:'result', winner:0, started:2000 }, 2000, manifest);
  assert.deepEqual(settled.camera, result.camera);
  assert.deepEqual(previewFrame(state, 0, manifest, true).camera, settled.camera);
});

for (const winner of [0,1]) {
  test(`P${winner+1}: camera follows launch, tracker uses projected position, reset is continuous`, () => {
    const state = { mode:'result', winner, started:0 }, loser=1-winner;
    const timing=resultTiming(manifest,winner);
    const first=previewFrame(state,0,manifest);
    const flight=previewFrame(state,(timing.hitAt+timing.hitlag+.3)*1000,manifest);
    assert.ok(flight.camera.zoom < first.camera.zoom);
    assert.ok(winner===0 ? flight.camera.x > 600 : flight.camera.x < 600);
    const nearBlast=previewFrame(state,(timing.koAt-.05)*1000,manifest);
    const projected=project(nearBlast.camera,nearBlast.positions[loser].x,nearBlast.positions[loser].y-140);
    assert.ok(projected.x < -40 || projected.x > 1240);
    assert.equal(nearBlast.magnifier.side,loser);
    const end=launchPosition(manifest,loser,1,HOME[loser]);
    assert.equal(end.x,600+manifest.stageInfo.blastBounds[loser===1?'right':'left']*GAME_UNIT);
    const before=previewFrame(state,timing.end*1000-.01,manifest);
    const after=previewFrame(state,timing.end*1000+.01,manifest);
    assert.ok(Math.abs(before.camera.zoom-after.camera.zoom)<1e-6);
    assert.ok(Math.abs(before.camera.x-after.camera.x)<1e-6);
  });
}

test('Roy forward smash keeps slash damage without introducing fire', () => {
  const roy=previewFrame({ mode:'result', winner:1, started:0 }, (resultTiming(manifest,1).hitAt+5.001/60)*1000, manifest);
  assert.equal(manifest.fighters.roy.move.hitboxes[0].Element,3); // HitElement_Slash
  assert.deepEqual(roy.positions[0].overlay,[255,255,255,70]);
  assert.ok(!roy.effects.some(effect=>effect.kind==='body-fire'));
  assert.equal(manifest.fighters['roy-left'].facing,'left');
});

for (const view of [VIEW,MOBILE_VIEW]) {
  for (const winner of [0,1]) {
    test(`${view.width}px P${winner+1}: one KO return, then a fixed camera through respawn and landing`, () => {
      const timing=resultTiming(manifest,winner), state={mode:'result',winner,started:0};
      let previous=0;
      for(let t=timing.koAt; t<timing.end; t+=1/60) {
        const frame=previewFrame(state,t*1000,manifest,false,view);
        assert.ok(frame.camera.zoom >= previous-1e-9, 'no zoom reversal during the return');
        previous=frame.camera.zoom;
      }
      for(const t of [0,.2,.7,1.1,1.4,1.8,2.5]) {
        const frame=previewFrame(state,(timing.end+t)*1000,manifest,false,view);
        assert.deepEqual(frame.camera,readyCamera(view,manifest,['dr-mario','roy-left']));
      }
      const flight=previewFrame(state,(timing.hitAt+timing.hitlag+.6)*1000,manifest,false,view);
      const survivor=project(flight.camera,flight.positions[winner].x,flight.positions[winner].y,view);
      assert.ok(survivor.x>=50 && survivor.x<=view.width-50, 'survivor stays visible while tracking');
    });
  }
  test(`${view.width}px: character tap targets contain their bodies and do not overlap`, () => {
    const targets=HOME.map(home=>fighterTarget(view,home,manifest,['dr-mario','roy-left']));
    assert.ok(targets[0].left+targets[0].width < targets[1].left);
    for(const target of targets) {
      assert.ok(target.left>=0 && target.left+target.width<=100);
      assert.ok(target.top>=0 && target.top+target.height<=100);
      assert.ok(target.width/100*(view.width===600?364:1200)>=44);
    }
  });
}

test('available roster bounds fit mobile during both platform hold and landing',()=>{
 const left=Object.entries(manifest.fighters).filter(([,f])=>f.facing==='right' && f.readyBounds);
 const right=Object.entries(manifest.fighters).filter(([,f])=>f.facing==='left' && f.readyBounds);
 for(const a of left)for(const b of right){
  const camera=readyCamera(MOBILE_VIEW,manifest,[a[0],b[0]]),homes=matchupHomes(manifest,[a[0],b[0]]);
  for(const [side,[,fighter]] of [a,b].entries()){
   const bounds=fighter.readyBounds,scale=1.62*fighterScale(fighter),anchor=fighter.anchor || [256,330];
   for(const floor of [150,456])for(const [x,y] of [[bounds[0],bounds[1]],[bounds[2],bounds[3]]]){
    const p=project(camera,homes[side]+(x-anchor[0])*scale,floor+(y-anchor[1])*scale,MOBILE_VIEW);
    assert.ok(p.x>=49 && p.x<=MOBILE_VIEW.width-49);
    assert.ok(p.y>=89 && p.y<=MOBILE_VIEW.height-79);
   }
  }
 }
});

test('KO overlay has a bounded, stable screen size and only 22 source quake frames',()=>{
  for(const view of [VIEW,MOBILE_VIEW]) {
    const state={mode:'result',winner:0,started:0};
    const timing=resultTiming(manifest,0);
    const samples=[.001,.1,.3,.6].map(age=>previewFrame(state,(timing.koAt+age)*1000,manifest,false,view));
    assert.ok(samples[0].ko.scale<3,'never use world-unit scaling for the edge overlay');
    assert.ok(samples.every(f=>f.ko.scale===samples[0].ko.scale));
    assert.ok(samples[1].shake.some(n=>n!==0));
    assert.deepEqual(samples.at(-1).shake,[0,0]);
  }
});

test('saved roster selections can render tap targets before assets load, including both Ice Climbers sides',()=>{
 for(const [key,fighter] of Object.entries(manifest.fighters)) {
  const side=fighter.facing==='left'?1:0,keys=['dr-mario','roy-left'];keys[side]=key;
  for(const view of [VIEW,MOBILE_VIEW]) {
   const target=fighterTarget(view,matchupHomes(undefined,keys)[side],undefined,keys);
   assert.ok(Object.values(target).every(Number.isFinite),key);
  }
 }
});
