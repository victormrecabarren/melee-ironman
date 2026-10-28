import { fighterScale } from './fighterScale.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { previewFrame, resultTiming, FLOOR, SPAWN_Y, LAUNCH_TIME, FIGHTERS,
  ENTRANCE_HOLD, FALL_TIME, PARTICLE_SCALE, IMPACT_PARTICLE_SCALE, damageModelOffset, releasePlatform } from './animationTimeline.js';
import { matchupHomes } from './combatSpacing.js';
const manifest = JSON.parse(readFileSync(new URL('../public/melee-preview/manifest.json', import.meta.url)));
const HOME=matchupHomes(manifest,FIGHTERS);

test('tapping the initial platforms starts a complete fall and brings GO forward',()=>{
  const state={mode:'entrance',started:1000,fighters:FIGHTERS,stocks:[2,2],matchStart:true};
  const released=releasePlatform(state,1200);
  assert.equal(released.started,state.started,'do not jump the animation clock');
  assert.equal(released.platformHoldSeconds,.2);
  const start=previewFrame(released,1200,manifest);
  assert.equal(start.platforms.length,0);
  assert.ok(start.positions.every(p=>p.clip==='fall' && Math.abs(p.y-SPAWN_Y)<.001));
  assert.ok(start.gameGo && Math.abs(start.gameGo.age)<1e-8);
  assert.equal(start.effects.some(e=>e.kind==='arrival-glow'),false);
  assert.equal(start.ready,false);
  const mid=previewFrame(released,1450,manifest);
  assert.ok(mid.positions.every(p=>p.y>SPAWN_Y && p.y<FLOOR));
  const landed=previewFrame(released,1701,manifest);
  assert.ok(landed.positions.every(p=>p.clip==='landing'));
  assert.equal(landed.effects.filter(e=>e.kind==='landing-dust').length,2);
  assert.deepEqual(landed.stocks,[2,2]);
  assert.equal(releasePlatform(released,1200),null,'repeated taps cannot skip the fall');
});

for(const winner of [0,1]) for(const fresh of [false,true]) {
  test(`early P${2-winner} ${fresh?'arrival':'revival'} preserves survivor taunt and stock counts`,()=>{
    const state={mode:'respawn',winner,started:1000,fighters:FIGHTERS,stocks:[2,2],tauntStarted:900,
      arrivals:winner===0?[false,fresh]:[fresh,false]};
    const released=releasePlatform(state,1300);
    const actual=previewFrame(released,1400,manifest),original=previewFrame(state,1400,manifest);
    assert.deepEqual(actual.positions[winner],original.positions[winner]);
    assert.deepEqual(actual.camera,original.camera);
    assert.equal(actual.positions[1-winner].clip,'fall');
    assert.equal(actual.platforms.length,0);
    assert.deepEqual(actual.stocks,state.stocks);
    assert.equal(actual.positions[1-winner].overlay!==undefined,!fresh);
  });
}

test('early drop is unavailable on the title card, after the wait, during a KO, or with reduced motion',()=>{
  const state={mode:'entrance',started:0};
  assert.equal(releasePlatform({...state,awaitingStart:true},200),null);
  assert.equal(releasePlatform(state,ENTRANCE_HOLD*1000),null);
  assert.equal(releasePlatform({...state,mode:'result'},200),null);
  assert.equal(releasePlatform(state,200,true),null);
});

for (const winner of [0, 1]) {
  test(`P${winner + 1}: result-to-respawn paints both fighters and preserves survivor idle`, () => {
    const state = { mode: 'result', winner, started: 1000 };
    const boundary = 1000 + resultTiming(manifest, winner).end * 1000;
    const before = previewFrame(state, boundary - 1, manifest);
    const after = previewFrame(state, boundary + 1, manifest);
    assert.equal(after.next.mode, 'respawn');
    assert.equal(after.positions.length, 2);
    const survivor = after.positions[winner];
    assert.equal(survivor.alpha, 1);
    assert.equal(survivor.x, HOME[winner]);
    assert.equal(survivor.y, FLOOR);
    assert.equal(survivor.clip, 'idle');
    assert.ok(Math.abs(survivor.time - before.positions[winner].time - .002) < .00001);
    assert.equal(after.positions[1-winner].y, SPAWN_Y);
    const following = previewFrame(after.next, boundary + 17, manifest);
    assert.ok(Math.abs(following.positions[winner].time - survivor.time - .016) < .00001);
  });
  test(`P${winner + 1}: hitstop, damage pose, then fast visible knockback`, () => {
    const state = { mode: 'result', winner, started: 0 };
    const { hitAt: hit, hitlag } = resultTiming(manifest, winner);
    const contact = previewFrame(state, (hit+.025)*1000, manifest);
    const held = previewFrame(state, (hit+.06)*1000, manifest);
    assert.equal(contact.positions[winner].time, held.positions[winner].time);
    assert.equal(Math.floor(contact.positions[winner].time * manifest.fighters[FIGHTERS[winner]].clips.smash.fps), resultTiming(manifest,winner).hits[0].frame);
    assert.equal(contact.positions[1-winner].clip, 'hit');
    assert.equal(contact.positions[1-winner].x, HOME[1-winner]);
    assert.equal(contact.positions[1-winner].time, 0);
    assert.equal(held.positions[1-winner].time, 0);
    assert.equal(held.positions[1-winner].loop, false);
    const flying = previewFrame(state, (hit+hitlag+.15)*1000, manifest);
    assert.equal(flying.positions[1-winner].clip, 'hit');
    assert.ok(Math.abs(flying.positions[1-winner].x-HOME[1-winner]) > 400);
    assert.equal(flying.positions[1-winner].alpha, 1);
    const gone = previewFrame(state, (hit+hitlag+LAUNCH_TIME+.001)*1000, manifest);
    assert.equal(gone.positions[1-winner].alpha, 0);
  });
  test(`P${winner+1}: offscreen tracker remains until the blast, then KO replaces it`, () => {
    const state = { mode: 'result', winner, started: 0 };
    const { koAt } = resultTiming(manifest, winner);
    const tracked = previewFrame(state, (koAt-.1)*1000, manifest);
    assert.equal(tracked.magnifier.side, 1-winner);
    assert.equal(tracked.ko, null);
    const dead = previewFrame(state, (koAt+.01)*1000, manifest);
    assert.equal(dead.magnifier, null);
    assert.equal(dead.ko.kind, `ko-p${2-winner}`);
    assert.ok(dead.sounds.some(cue => cue.id === 'ko'));
  });
  test(`P${winner+1}: only the respawning fighter gets the source color overlay and landing dust`, () => {
    const state = { mode: 'respawn', winner, started: 0 };
    const onPlatform = previewFrame(state, 100, manifest);
    assert.ok(onPlatform.positions[1-winner].overlay);
    assert.equal(onPlatform.positions[winner].overlay, undefined);
    const touchdown = (ENTRANCE_HOLD+FALL_TIME)*1000;
    const landed = previewFrame(state, touchdown+1, manifest);
    assert.equal(landed.effects.filter(e => e.kind === 'landing-dust').length, 1);
    assert.equal(landed.positions[1-winner].clip, 'landing');
    assert.ok(landed.positions[1-winner].overlay);
    assert.equal(previewFrame(state, touchdown+220, manifest).effects.length, 0);
    assert.equal(previewFrame(state, (ENTRANCE_HOLD+2)*1000+1, manifest).positions[1-winner].overlay, undefined);
  });
}
test('entrance reaches a playable state; reduced motion skips motion and effects', () => {
  assert.equal(previewFrame({ mode: 'entrance', started: 0 }, 2500, manifest).ready, true);
  const entrance = previewFrame({ mode: 'entrance', started: 0 }, 0, manifest, true);
  assert.equal(entrance.ready, true);
  assert.equal(entrance.platforms.length, 0);
  const result = previewFrame({ mode: 'result', winner: 0, started: 0 }, 300, manifest, true);
  assert.equal(result.impact, null);
  assert.equal(result.positions[0].x, HOME[0]);
  assert.deepEqual(result.effects, []);
  assert.deepEqual(result.sounds, []);
  assert.equal(result.magnifier, null);
});
test('fresh arrivals use the original trophy pedestal at revival height without invincibility',()=>{
  assert.equal(manifest.environment.arrival.source.root,'ftLoadCommonData+0x40');
  assert.notEqual(manifest.environment.arrival.file,manifest.environment.revival.file);
  for(const fighter of Object.values(manifest.fighters))assert.ok(fighter.arrivalPlatformScale>0);
  const state={mode:'entrance',started:0,fighters:FIGHTERS,stocks:[2,2]};
  const onPlatform=previewFrame(state,100,manifest);
  assert.equal(onPlatform.platforms.length,2);
  for(const p of onPlatform.platforms){assert.equal(p.kind,'arrival');assert.equal(p.y,SPAWN_Y+4);}
  assert.ok(onPlatform.effects.every(e=>e.kind==='arrival-glow'));
  assert.ok(onPlatform.positions.every(p=>p.overlay?.[3]===120),'original entry glow, not revival flicker');
  for(const t of [1100,1551,1900]){
    const frame=previewFrame(state,t,manifest);
    assert.ok(frame.positions.every(p=>p.overlay===undefined));
  }
  const landed=previewFrame(state,1551,manifest);
  assert.equal(landed.effects.filter(e=>e.kind==='landing-dust').length,2);
});
test('GO uses the original HUD and announcer only for a new match, never for respawns',()=>{
  const state={mode:'entrance',started:0,fighters:FIGHTERS,stocks:[2,2],matchStart:true,awaitingStart:true};
  const waiting=previewFrame(state,90000,manifest);
  assert.equal(waiting.ready,false);assert.equal(waiting.gameGo,undefined);assert.deepEqual(waiting.sounds,[]);
  state.awaitingStart=false;
  assert.equal(previewFrame(state,100,manifest).gameGo,undefined);
  const go=previewFrame(state,(ENTRANCE_HOLD+.2)*1000,manifest);
  assert.ok(go.gameGo);assert.ok(go.sounds.some(c=>c.id==='go-announcer'));
  assert.equal(manifest.audio['go-announcer'].soundId,510039);
  assert.match(manifest.environment['game-go'].source,/scene_models\[4\]/);
  assert.equal(previewFrame(state,3000,manifest).gameGo,undefined);
  assert.equal(previewFrame({...state,matchStart:false},1250,manifest).gameGo,undefined);
  assert.equal(previewFrame({...state,mode:'respawn',winner:0},1250,manifest).gameGo,undefined);
});
for(const winner of [0,1])test(`P${winner+1}: final stock brings a fresh arrival, one stock lost brings a revival`,()=>{
  const loser=1-winner;
  const nextFighters=[...FIGHTERS];nextFighters[loser]=loser===0?'mario':'marth-left';
  for(const fresh of [false,true]){
    const state={mode:'result',started:0,winner,fighters:FIGHTERS,stocks:[2,2],
      nextFighters:fresh?nextFighters:FIGHTERS,nextStocks:[2,2].map((n,i)=>i===loser&&!fresh?1:n)};
    const now=resultTiming(manifest,winner).end*1000+1;
    const frame=previewFrame(state,now,manifest);
    assert.equal(frame.platforms[0].kind,fresh?'arrival':'revival');
    assert.equal(frame.next.arrivals[loser],fresh);
    assert.equal(frame.effects.some(e=>e.kind==='arrival-glow'),fresh);
    const dropped=previewFrame(frame.next,frame.next.started+1551,manifest);
    assert.equal(dropped.positions[loser].overlay===undefined,fresh);
    assert.equal(dropped.positions[loser].clip,'landing');
  }
});
test('source data keeps electric and slash moves distinct and uses game hitlag', () => {
  assert.equal(manifest.fighters['dr-mario'].move.hitboxes[0].Element, 2);
  assert.equal(manifest.fighters.roy.move.hitboxes[0].Element, 3);
  assert.equal(resultTiming(manifest, 0).hitlag, 13/60);
  assert.equal(resultTiming(manifest, 1).hitlag, 9/60);
  assert.equal(manifest.common.postDropFrames, 120);
  assert.deepEqual(manifest.common.platformOverlay.rgba[0], [255,255,255,255]);
  assert.deepEqual(manifest.common.platformOverlay.rgba[37], [255,255,255,10]);
  assert.deepEqual(manifest.common.postDropOverlay.rgba[7], [0,0,0,0]);
});

test('respawn overlay is gone by inspection frame 130, with original cycle speed', () => {
  const state = { mode: 'respawn', winner:1, started: 0, stocks:[1,2] };
  assert.ok(previewFrame(state, 100/60*1000, manifest).positions[0].overlay);
  assert.equal(previewFrame(state, 130/60*1000, manifest).positions[0].overlay, undefined);
});
test('electric damage tint follows the original alternating blue-white script only on victim', () => {
  const state = { mode: 'result', winner: 0, started: 0 };
  const blue = previewFrame(state, 12/60*1000, manifest);
  const white = previewFrame(state, 13.01/60*1000, manifest);
  assert.deepEqual(blue.positions[1].overlay, [0, 0, 148, 90]);
  assert.deepEqual(white.positions[1].overlay, [255, 255, 255, 70]);
  assert.equal(blue.positions[0].overlay, undefined);
  assert.equal(blue.positions[1].clip, 'hit');
  assert.equal(blue.positions[1].time, 0);
  assert.deepEqual(previewFrame({ ...state, winner: 1 }, resultTiming(manifest,1).hitAt*1000, manifest).positions[0].overlay, [0,0,0,0]);
});

test('Doc hand electricity stays attached and above his hand throughout hitstop', () => {
  const state = { mode: 'result', winner: 0, started: 0 };
  const { hitAt, hitlag } = resultTiming(manifest, 0);
  for (const elapsed of [0, .08, hitlag-.001]) {
    const frame = previewFrame(state, (hitAt+elapsed)*1000, manifest);
    const hand = frame.effects.filter(effect => effect.kind === 'hand-electric' && effect.afterFighter === 0);
    assert.equal(hand.length, 2, 'retain both original move events');
    const anchor = manifest.fighters['dr-mario'].move.attachments[12]['1042'];
    assert.equal(hand[0].x, frame.positions[0].x+(anchor[0]-256)*1.62*fighterScale(manifest.fighters['dr-mario']));
    assert.equal(hand[0].y, frame.positions[0].y+(anchor[1]-330)*1.62*fighterScale(manifest.fighters['dr-mario']));
    assert.equal(hand[0].scale, PARTICLE_SCALE);
    assert.equal(hand[0].scale, IMPACT_PARTICLE_SCALE, 'burst and body sparks use the same game-unit projection');
  }
});

test('electric hitlag shifts the victim model while holding its pose and world position', () => {
  const state = { mode: 'result', winner: 0, started: 0 };
  const { hitAt, hitlag } = resultTiming(manifest, 0);
  const frames = Array.from({ length: 13 }, (_, i) => previewFrame(state, (hitAt+(i+.01)/60)*1000, manifest));
  assert.equal(manifest.common.damageModelShift.tables.electric.length, 5);
  assert.deepEqual(manifest.common.damageModelShift.tables.electric[2], [0, 5]);
  for (const frame of frames) {
    assert.equal(frame.positions[1].time, 0);
    assert.equal(frame.positions[1].x, HOME[1]);
    assert.equal(frame.positions[1].y, FLOOR);
    assert.equal(frame.positions[0].modelOffset, undefined);
  }
  assert.notDeepEqual(frames[0].positions[1].modelOffset, frames[1].positions[1].modelOffset);
  assert.deepEqual(frames[0].positions[1].modelOffset, frames[5].positions[1].modelOffset);
  assert.ok(frames[2].positions[1].modelOffset[1] < 0, 'positive game Y shifts upward on canvas');
  assert.deepEqual(damageModelOffset(manifest, 16/60, hitlag, true, -1), [0, 0]);
  const left = damageModelOffset(manifest, 1/60, hitlag, true, -1);
  const right = damageModelOffset(manifest, 1/60, hitlag, true, 1);
  assert.equal(left[0], -right[0]);
  assert.equal(left[1], right[1]);
});


test('Roy contact uses original normal damage flash, then advances the held source pose', () => {
  const state={mode:'result',winner:1,started:0};
  const {hitAt,hitlag}=resultTiming(manifest,1);
  const contact=previewFrame(state,(hitAt+1.01/60)*1000,manifest);
  assert.deepEqual(contact.positions[0].overlay,[255,255,255,170]);
  assert.equal(contact.positions[0].time,0);
  const release=previewFrame(state,(hitAt+hitlag+.001)*1000,manifest);
  assert.equal(release.positions[0].clip,contact.positions[0].clip);
  assert.ok(release.positions[0].time>0 && release.positions[0].time<1/60);
  const late=previewFrame(state,(hitAt+hitlag+.7)*1000,manifest);
  assert.equal(late.magnifier.clip,'hit');
  assert.equal(late.magnifier.loop,false,'do not restart the contact pose in the tracker');
});

test('all installed damage reactions retain body attachment points and tracker framing', () => {
  for(const [key,fighter] of Object.entries(manifest.fighters)) {
    const clip=fighter.clips.hit;
    assert.equal(clip.source,'DamageFlyN',key);
    assert.equal(clip.damageAnchors.length,clip.frames,key);
    assert.equal(clip.frameCenters.length,clip.frames,key);
    assert.ok(clip.damageAnchors.every(points=>points.length===5 && points.flat().every(Number.isFinite)),key);
  }
  const {hitAt}=resultTiming(manifest,0);
  const frame=previewFrame({mode:'result',winner:0,started:0},(hitAt+.05)*1000,manifest);
  assert.ok(frame.effects.some(effect=>effect.kind==='hand-electric' && effect.afterFighter===1),'victim electricity remains visible over its damaged silhouette');
});

test('Mario fire remains at its emission point as the victim launches',()=>{
  const fighters=['mario','roy'];
  const state={mode:'result',winner:0,started:0,fighters};
  const {hitAt,hitlag}=resultTiming(manifest,0,fighters);
  const a=previewFrame(state,(hitAt+hitlag+.02)*1000,manifest);
  const b=previewFrame(state,(hitAt+hitlag+.05)*1000,manifest);
  const first=frame=>frame.effects.find(e=>e.kind==='body-fire' && e.emissionFrame===0);
  assert.ok(a.effects.some(e=>e.kind==='hand-fire'));
  assert.deepEqual([first(a).x,first(a).y],[first(b).x,first(b).y]);
  assert.notEqual(a.positions[1].x,b.positions[1].x);
});

test('KO atlases stay inside the mobile decoded-memory budget',()=>{
  let bytes=0;
  for(const name of ['ko-p1','ko-p2','ko-particles']) {
    const clip=manifest.environment[name];
    assert.equal(clip.rects.length,clip.frames);
    const [width,height]=clip.decodedSize;bytes+=width*height*4;
    assert.ok(width<=2048 && height<=2048);
    for(const [x,y,w,h,dx,dy] of clip.rects) {
      assert.ok(x+w<=width && y+h<=height);
      assert.ok(dx+w<=clip.width && dy+h<=clip.height);
    }
  }
  assert.ok(bytes<16*1024*1024,'all three KO atlases combined must stay below 16 MiB decoded');
  assert.equal(manifest.environment.ko,undefined,'do not load unused uncolored intermediate');
});

test('Zelda early hits use visible recoil and advance between individual hitstop windows',()=>{
 const fighters=['zelda','roy-left'],state={mode:'result',winner:0,started:0,fighters};
 const timing=resultTiming(manifest,0,fighters),[first,second]=timing.hits;
 assert.ok(timing.hits.length>1);
 const start=previewFrame(state,(first.at+.001)*1000,manifest).positions[1];
 assert.equal(start.clip,'recoil');
 assert.ok(start.time>=1/manifest.fighters['roy-left'].clips.recoil.fps,'skip neutral transition sample');
 const held=previewFrame(state,(first.at+first.hitlag/2)*1000,manifest).positions[1];
 assert.equal(held.time,start.time);
 const between=previewFrame(state,(first.at+first.hitlag+.5/60)*1000,manifest).positions[1];
 assert.ok(between.time>held.time);
 const again=previewFrame(state,(second.at+.001)*1000,manifest).positions[1];
 assert.equal(again.time,start.time,'new contact restarts the visible recoil');
});

for(const [slug,gate,damage] of [['link',19,[13,18]],['young-link',20,[10,12]]]) {
  for(const winner of [0,1]) {
    test(`${slug} P${winner+1}: original follow-up hits twice, recoils first, launches only on finisher`,()=>{
      const fighters=winner===0?[slug,'roy-left']:['roy',slug+'-left'];
      const fighter=manifest.fighters[fighters[winner]],move=fighter.move;
      assert.equal(fighter.clips.smash.source,'AttackS41+AttackS42');
      assert.deepEqual(move.sequence.map(s=>[s.action,s.start]),[['AttackS41',0],['AttackS42',gate]]);
      assert.deepEqual(move.hitPhases.map(p=>[p.frame,p.hitbox.Damage]),[[15,damage[0]],[gate+10,damage[1]]]);
      assert.equal(move.trail.ranges.length,2,'retain both original sword afterimage windows');
      assert.deepEqual(fighter.clips.smash.clippedFrames,[]);
      assert.equal(move.attachments.length,fighter.clips.smash.frames);
      const state={mode:'result',winner,started:0,fighters,stocks:[2,2]};
      const timing=resultTiming(manifest,winner,fighters),[first,last]=timing.hits;
      assert.equal(timing.hits.length,2);
      assert.equal(last.at,last.frame/60+first.hitlag,'second source clock includes first hitstop');
      const sample=t=>previewFrame(state,t*1000,manifest);
      const start=sample(first.at+.001),held=sample(first.at+first.hitlag/2);
      assert.equal(start.positions[1-winner].clip,'recoil');
      assert.equal(held.positions[1-winner].time,start.positions[1-winner].time);
      const between=sample(last.at-.001);
      assert.equal(between.positions[1-winner].clip,'recoil');
      assert.ok(between.positions[1-winner].time>held.positions[1-winner].time);
      assert.equal(between.positions[1-winner].x,start.positions[1-winner].x,'no early launch');
      assert.equal(between.ko,null);
      const finish=sample(last.at+.001);
      assert.equal(finish.positions[1-winner].clip,'hit');
      assert.equal(finish.positions[1-winner].time,0,'finisher holds the source launch pose during hitstop');
      assert.equal(finish.positions[winner].time,last.frame/60);
      assert.equal(finish.impact.damage,damage[1]);
      const flying=sample(last.at+last.hitlag+.15);
      assert.ok(Math.abs(flying.positions[1-winner].x-finish.positions[1-winner].x)>400);
      assert.deepEqual(flying.stocks,[2,2],'do not count either sword contact as a stock yet');
      const ko=sample(timing.koAt+.001);
      assert.equal(ko.stocks[1-winner],1,'only the final KO removes a stock');
    });
  }
}

for(const winner of [0,1]) {
  test(`P${winner+1}: Game! begins at KO while blast and quake finish without a camera reset`,()=>{
    const state={mode:'result',winner,started:1000,finishedRun:true,stocks:winner===0?[2,1]:[1,2]};
    const {koAt}=resultTiming(manifest,winner);
    const at=state.started+koAt*1000;
    const before=previewFrame(state,at-1,manifest);
    assert.equal(before.complete,undefined);
    assert.equal(before.ko,null);
    const start=previewFrame(state,at,manifest);
    const during=previewFrame(state,at+100,manifest);
    const quakeEnd=manifest.common.koQuake.offsets.length/manifest.common.koQuake.fps;
    const settled=previewFrame(state,at+quakeEnd*1000,manifest);
    const later=previewFrame(state,at+5000,manifest);
    assert.equal(start.complete,true);
    assert.ok(start.gameEnd.age<1e-9);
    assert.equal(later.next,undefined);
    assert.equal(later.stocks[1-winner],0);
    for(const frame of [during,settled,later]) {
      assert.deepEqual(frame.camera,start.camera,'no return-to-respawn zoom');
      assert.deepEqual(frame.positions,start.positions,'fighters remain at final KO');
    }
    assert.ok(during.ko.age>start.ko.age,'explosion advances');
    const blast=manifest.environment[later.ko.kind];
    const particles=manifest.environment['ko-particles'];
    assert.ok(later.ko.age>=Math.max(blast.frames/blast.fps,particles.frames/particles.fps),'both blast layers finish');
    assert.deepEqual(settled.shake,[0,0]);
    assert.deepEqual(later.shake,[0,0]);
    assert.ok(Array.from({length:Math.ceil(quakeEnd*60)},(_,i)=>previewFrame(state,at+i*1000/60,manifest).shake).some(v=>v.some(n=>n!==0)),'source rumble still plays');
    assert.ok(later.stockLoss.age>during.stockLoss.age,'stock removal finishes');
    assert.equal(start.sounds.some(c=>c.id==='game-announcer'),false);
    assert.equal(later.sounds.filter(c=>c.id==='game-announcer').length,1);
  });
}
test('reduced motion final stock completes without respawning',()=>{
  const state={mode:'result',winner:0,started:0,finishedRun:true,stocks:[2,1]};
  const frame=previewFrame(state,5000,manifest,true);
  assert.equal(frame.complete,true);assert.equal(frame.next,undefined);
  assert.deepEqual(frame.stocks,[2,0]);assert.ok(frame.gameEnd);
});
test('Game! uses the US disc graphic and original announcer sample',()=>{
  const clip=manifest.environment['game-end'];
  assert.match(clip.source,/IfAll\.usd: ScInfCnt_scene_models\[5\]/);
  assert.equal(clip.appearAfterKoFrames,0);
  assert.equal(clip.announcerDelayFrames,8);
  assert.ok(clip.pages.every(p=>p.width<=2048 && p.height<=2048));
  assert.equal(manifest.audio['game-announcer'].soundId,510037);
  const wav=readFileSync(new URL('../public/melee-preview/game-announcer.wav',import.meta.url));
  assert.equal(wav.toString('ascii',0,4),'RIFF');
  assert.equal(wav.toString('ascii',8,12),'WAVE');
  assert.ok(manifest.audio['game-announcer'].duration>.5);
});
