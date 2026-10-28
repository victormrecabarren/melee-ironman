import { fighterScale } from './fighterScale.js';
import {chargeProgress} from './smashInteraction.js';
import { clipFiles, spriteFrame } from './spriteAtlas.js';
import { companionPosition, fighterAssetKeys } from './previewCompanions.js';
import { matchupHomes } from './combatSpacing.js';
import React, { useEffect, useRef, useState } from 'react';
import './App.css';
import {readPreviewSession, capturePreviewSession, restorePreviewPlayback, writePreviewSession, freshPreviewSession} from './previewSession.js';
import { FIGHTERS, FLOOR, IMPACT_PARTICLE_SCALE, previewFrame, resultTiming, releasePlatform } from './animationTimeline.js';
import { advanceAnimationClock, resetAnimationClock, animationFrameIndex } from './animationClock.js';
import { CHARACTER_ROSTER, initialLineup, lineupCharacter, lineupFighters, takeStock, withPlayedCharacters, playerStockStats } from './previewRoster.js';
import { stageScale, FIGHTER_SCALE, VIEW, MOBILE_VIEW, fighterTarget } from './previewCamera.js';

const BASE = `${import.meta.env.BASE_URL}melee-preview/`;
function environmentSprite(ctx, assets, kind, seconds, x, y, scale = 1, loop = false) {
  const clip = assets.manifest.environment[kind];
  let frame = animationFrameIndex(seconds, clip.fps);
  frame = loop ? frame % clip.frames : Math.min(frame, clip.frames - 1);
  if(clip.pages) {
    const r=spriteFrame(clip,frame,clip);
    if(r.width && r.height)ctx.drawImage(assets.images[r.file],r.x,r.y,r.width,r.height,
      x+(r.dx-clip.anchor[0])*scale,y+(r.dy-clip.anchor[1])*scale,r.width*scale,r.height*scale);
    return;
  }
  if (clip.rects) {
    const [sx, sy, w, h, dx, dy] = clip.rects[frame];
    if (w && h) ctx.drawImage(assets.images[clip.file], sx, sy, w, h,
      x+(dx-clip.anchor[0])*scale, y+(dy-clip.anchor[1])*scale, w*scale, h*scale);
    return;
  }
  ctx.drawImage(assets.images[clip.file], (frame % clip.columns) * clip.width,
    Math.floor(frame / clip.columns) * clip.height, clip.width, clip.height,
    x - clip.anchor[0] * scale, y - clip.anchor[1] * scale,
    clip.width * scale, clip.height * scale);
}

function paintSky(ctx, view) {
  ctx.clearRect(0, 0, view.width, view.height);
  const sky = ctx.createLinearGradient(0, 0, 0, view.height);
  sky.addColorStop(0, '#080818'); sky.addColorStop(.65, '#191a32'); sky.addColorStop(1, '#0b0c16');
  ctx.fillStyle = sky; ctx.fillRect(0, 0, view.width, view.height);
  for (let i = 0; i < 90; i++) {
    ctx.fillStyle = `rgba(225,224,255,${.14 + (i % 5) * .07})`;
    ctx.fillRect((i * 137.508 + 31) % view.width, (i * 73.17 + 15) % (view.height*.7), i % 4 === 0 ? 2 : 1, 1);
  }
}

function paintImpact(ctx, assets, impact) {
  if (!impact) return;
  const { age, x, y, winner } = impact;
  const kind = ({0:'normal-impact',1:'fire-impact',2:'electric',3:'slash',13:'dark-impact'})[impact.element] || 'normal-impact';
  const clip = assets.manifest.environment[kind];
  if (!clip) return;
  ctx.save(); ctx.globalCompositeOperation = kind==='slash' || (kind==='normal-impact' && !clip.pixelsPerGameUnit) ? 'screen' : 'source-over';
  if (age < clip.frames / clip.fps) {
    const size=clip.damageScale;
    const damageScale=size ? Math.max(size.minimum,Math.min(size.maximum,size.base+size.multiplier*impact.damage)) : 1;
    environmentSprite(ctx, assets, kind, age, x, y,
      (clip.pixelsPerGameUnit ? 17.28/clip.pixelsPerGameUnit : IMPACT_PARTICLE_SCALE/2)*damageScale);
  }
  ctx.restore();
}

function sprite(ctx, assets, side, clipName, seconds, x, ground, { loop = false, alpha = 1, tilt = 0, overlay, scale = 1.62, modelOffset = [0, 0], fighter: fighterKey } = {}) {
  const fighter = assets.manifest.fighters[fighterKey || FIGHTERS[side]];
  const clip = fighter.clips[clipName];
  scale *= fighterScale({...fighter,scale:clip.exportScale ?? fighter.scale});
  const anchor=clip.anchor || fighter.anchor || [256,330];
  let frame = animationFrameIndex(seconds, clip.fps || assets.manifest.fps);
  frame = loop ? frame % clip.frames : Math.min(frame, clip.frames - 1);
  const rect=spriteFrame(clip,frame,assets.manifest);
  if(!rect.width || !rect.height)return;
  const image = assets.images[rect.file];
  const { width, height } = assets.manifest;
  ctx.save(); ctx.translate(x+modelOffset[0], ground+modelOffset[1]); ctx.rotate(tilt);
  const facing = fighter.facing || 'right';
  const mirror = facing !== (side === 0 ? 'right' : 'left');
  ctx.scale(mirror ? -scale : scale, scale); ctx.globalAlpha = alpha;
  const {x:sx,y:sy,width:sw,height:sh,dx,dy}=rect;
  if (overlay?.[3]) {
    const tint = assets.tint.getContext('2d');
    tint.clearRect(0, 0, width, height);
    tint.drawImage(image, sx, sy, sw, sh, dx, dy, sw, sh);
    // Source color-overlay RGBA cycle; preserve the fighter's silhouette.
    tint.globalCompositeOperation = 'source-atop';
    tint.fillStyle = `rgba(${overlay[0]},${overlay[1]},${overlay[2]},${overlay[3]/255})`;
    tint.fillRect(0, 0, width, height); tint.globalCompositeOperation = 'source-over';
    ctx.drawImage(assets.tint, -anchor[0], -anchor[1]);
  } else ctx.drawImage(image, sx, sy, sw, sh, dx-anchor[0], dy-anchor[1], sw, sh);
  ctx.restore();
}

function paintMagnifier(ctx, assets, tracker) {
  if (!tracker) return;
  const mini = assets.magnifier.getContext('2d');
  mini.clearRect(0, 0, 256, 256);
  const fighter=assets.manifest.fighters[tracker.fighter || FIGHTERS[tracker.side]];
  const clip=fighter.clips[tracker.clip];
  const anchor=fighter.anchor || [256,330], scale=.68*fighterScale(fighter);
  const elapsed = animationFrameIndex(tracker.time,clip.fps);
  const index = tracker.loop ? elapsed%clip.frames : Math.min(elapsed,clip.frames-1);
  const center = clip.frameCenters[index];
  const miniature={...tracker,x:128-(center[0]-anchor[0])*scale,y:128-(center[1]-anchor[1])*scale};
  const partner=companionPosition(miniature,tracker.side,assets.manifest);
  if(partner) sprite(mini,assets,tracker.side,partner.clip,partner.time,
    miniature.x+(partner.x-miniature.x)*.68/1.62,miniature.y,{...partner,scale:.68});
  sprite(mini, assets, tracker.side, tracker.clip, tracker.time,
    miniature.x,miniature.y,{ loop: tracker.loop, scale: .68, overlay: tracker.overlay, fighter:tracker.fighter });
  mini.globalCompositeOperation = 'destination-in';
  const mask=assets.manifest.environment['magnifier-mask'];
  environmentSprite(mini,assets,'magnifier-mask',0,mask.anchor[0],mask.anchor[1]);
  mini.globalCompositeOperation = 'source-over';
  ctx.save(); ctx.translate(tracker.x, tracker.y); ctx.scale(.78, .78);
  ctx.drawImage(assets.magnifier, -128, -128);
  // Mirror only the original HUD frame/arrow, never the fighter's handedness.
  ctx.scale(tracker.sign, 1);
  environmentSprite(ctx, assets, 'magnifier', 0, 0, 0);
  ctx.restore();
}

function draw(ctx, assets, state, now, reducedMotion, view) {
  const frame = previewFrame(state, now, assets.manifest, reducedMotion, view);
  paintSky(ctx, view);
  const camera=frame.camera;
  ctx.save();ctx.translate(frame.shake?.[0] || 0,frame.shake?.[1] || 0);ctx.translate(view.width/2,view.height/2);ctx.scale(camera.zoom,camera.zoom);ctx.translate(-camera.x,-camera.y);
  environmentSprite(ctx, assets, 'stage', 0, 600, FLOOR, stageScale(assets.manifest));
  for (const platform of frame.platforms) {
    ctx.save();
    const side=frame.positions.findIndex(p=>p.x===platform.x);
    const partner=side>=0 && companionPosition(frame.positions[side],side,assets.manifest);
    environmentSprite(ctx, assets, platform.kind, reducedMotion ? 0 : platform.time,
      partner?(platform.x+partner.x)/2:platform.x, platform.y, (512/4.8*FIGHTER_SCALE)/(512/2)*platform.scale, true);
    ctx.restore();
  }
  function paintEffect(effect) {
    ctx.save(); ctx.globalCompositeOperation = effect.kind.endsWith('dust') || effect.kind === 'smash-ground' ? 'screen' : 'source-over';
    ctx.translate(effect.x, effect.y);
    if (effect.kind === 'dust' || effect.kind==='charge-dust' || effect.kind==='taunt-step-dust') ctx.scale(effect.sign, 1);
    environmentSprite(ctx, assets, effect.kind, effect.age, 0, 0, effect.scale);
    ctx.restore();
  }
  // Ground/impact effects stay behind the fighters. Hand-attached electricity
  // must be over its owner's hand, but still underneath the struck fighter.
  for (const effect of frame.effects.filter(effect => effect.afterFighter === undefined && effect.afterCompanion === undefined)) {
    paintEffect(effect);
    if(effect.kind==='landing-dust') {
      const side=frame.positions.findIndex(p=>p.x===effect.x);
      const partner=side>=0 && companionPosition(frame.positions[side],side,assets.manifest);
      if(partner) paintEffect({...effect,x:partner.x});
    }
  }
  for(const impact of frame.impacts || [frame.impact]) paintImpact(ctx,assets,impact);
  const fighterOrder = frame.impact ? [frame.impact.winner, 1-frame.impact.winner] : [0, 1];
  for (const side of fighterOrder) {
    const p = frame.positions[side];
    const partner=companionPosition(p,side,assets.manifest);
    if(partner) {
      sprite(ctx,assets,side,partner.clip,reducedMotion?0:partner.time,partner.x,partner.y,partner);
      for(const effect of frame.effects.filter(e=>e.afterCompanion===side)) paintEffect(effect);
      // Damage particles use Nana's own exported body anchors.
      const clip=assets.manifest.fighters[partner.fighter].clips[partner.clip];
      const points=clip.damageAnchors?.[Math.min(Math.floor(partner.time*clip.fps),clip.frames-1)];
      const source=assets.manifest.fighters[partner.fighter],origin=source.anchor || [256,330],scale=1.62*fighterScale(source);
      for(const [index,effect] of frame.effects.filter(e=>e.afterFighter===side && e.emissionFrame!==undefined).entries()) {
        if(!points)continue;
        if(effect.kind==='body-fire') { paintEffect({...effect,x:effect.x+partner.x-p.x}); continue; }
        const anchor=points[index%points.length],offset=partner.modelOffset || [0,0];
        paintEffect({...effect,x:partner.x+offset[0]+(anchor[0]-origin[0])*scale,
          y:partner.y+offset[1]+(anchor[1]-origin[1])*scale});
      }
    }
    sprite(ctx, assets, side, p.clip, reducedMotion ? 0 : p.time, p.x, p.y, p);
    for (const effect of frame.effects.filter(effect => effect.afterFighter === side)) paintEffect(effect);
  }
  ctx.restore();
  paintMagnifier(ctx, assets, frame.magnifier);
  paintStocks(ctx, assets, frame, view);
  if (frame.ko) {
    const ko = frame.ko;
    ctx.save(); ctx.globalCompositeOperation = 'screen'; ctx.translate(ko.x, ko.y);
    // Game Z rotation is counterclockwise; canvas Y points down, so invert it.
    // The blast originates outside the camera and its wave travels inward.
    ctx.rotate(-ko.sign * Math.PI/2);
    const model=assets.manifest.environment[ko.kind];
    if(ko.age<model.frames/model.fps) environmentSprite(ctx, assets, ko.kind, ko.age, 0, 0, ko.scale);
    const particles=assets.manifest.environment['ko-particles'];
    if(particles && ko.age<particles.frames/particles.fps) environmentSprite(ctx,assets,'ko-particles',ko.age,0,0,ko.scale);
    ctx.restore();
  }
  if (frame.gameEnd && assets.manifest.environment['game-end']) {
    const clip=assets.manifest.environment['game-end'];
    environmentSprite(ctx,assets,'game-end',frame.gameEnd.age,view.width/2,view.height/2,
      Math.min(view.width*.94/clip.width,view.height*.42/clip.height));
  }
  if(frame.gameGo){
    const clip=assets.manifest.environment['game-go'];
    environmentSprite(ctx,assets,'game-go',frame.gameGo.age,view.width/2,view.height/2,
      Math.min(view.width*.94/clip.width,view.height*.42/clip.height));
  }
  return frame;
}

async function loadFighterImages(assets,keys) {
  const needed=new Set();
  for(const key of fighterAssetKeys(keys)) {
    const fighter=assets.manifest.fighters[key];
    if(!fighter)throw new Error(`The assets for ${key} are not ready yet.`);
    for(const clip of Object.values(fighter.clips)) for(const file of clipFiles(clip)) needed.add(file);
  }
  await Promise.all([...needed].map(async file=>{
    if(assets.images[file])return;
    const image=new Image();image.src=BASE+file;await image.decode();assets.images[file]=image;
  }));

}

function retainFighterImages(assets,keys) {
  const needed=new Set(fighterAssetKeys(keys).flatMap(key=>Object.values(assets.manifest.fighters[key]?.clips || {}).flatMap(clipFiles)));
  for(const file of assets.fighterFiles)if(!needed.has(file))delete assets.images[file];
}

function paintStocks(ctx,assets,frame,view) {
  frame.positions.forEach((position,side)=>{
    const fighter=assets.manifest.fighters[position.fighter];
    const kind='stock-'+(fighter.slug || position.fighter.replace(/-left$/,''));
    const clip=assets.manifest.environment[kind];
    if(!clip)return;
    for(let index=0;index<2;index++) {
      const loss=frame.stockLoss?.side===side && frame.stockLoss.index===index ? frame.stockLoss : null;
      if(index>=frame.stocks[side] && !loss)continue;
      const x=side===0 ? 40+index*42 : view.width-40-index*42;
      const lossFrame=loss?Math.floor(loss.age*60):0, offset=loss?clip.lossOffsets[Math.min(lossFrame,10)]:[0,0];
      if(!loss || lossFrame<clip.lossFrames)environmentSprite(ctx,assets,kind,0,x+offset[0]*16,48-offset[1]*16,.8);
      if(loss && assets.manifest.environment['stock-loss'] && loss.age<.6)
        environmentSprite(ctx,assets,'stock-loss',loss.age,x,48,.45);
    }
  });
}

function StockPortrait({character,assets,label=false}) {
  const clip=assets?.manifest.environment['stock-'+character.slug];
  return clip ? <img className="stats-stock-icon" src={BASE+(clip.sourceAtlas || clip.file)}
    width="28" height="28" alt={label?character.name:''} title={character.name} /> : null;
}

function MatchStats({lineup,assets}) {
  return <section className="match-stats" aria-label="Player stock stats">
    <div className="match-stats-heading"><h2>Stocks taken</h2><span>{lineup.champion!==null?'Final results':'This match'}</span></div>
    <div className="match-stats-sides">{[0,1].map(side=>{
      const rows=playerStockStats(lineup,side);
      const total=rows.reduce((sum,row)=>sum+row.victims.length,0);
      return <section className={`match-stats-side stats-side-${side}`} key={side} aria-label={`Player ${side+1} stats`}>
        <header><h3><i />Player {side+1}</h3><span>{total} {total===1?'stock':'stocks'}</span></header>
        <ol className="match-stats-rows">{rows.map(({character,victims})=><li key={character.slug}>
          <div className="stats-character"><StockPortrait character={character} assets={assets}/><span>{character.name}</span></div>
          <strong className="stats-count" aria-label={`${victims.length} stocks taken`}>{victims.length}</strong>
          <div className="stats-victims" aria-label={`Stocks taken by ${character.name}`}>
            {victims.length? victims.map((victim,index)=><StockPortrait key={index} character={victim} assets={assets} label/>):<span className="stats-empty">No stocks taken</span>}
          </div>
        </li>)}</ol>
      </section>;
    })}</div>
  </section>;
}

export default function App() {
  const canvas = useRef(null), inspector=useRef(null), devTools=useRef(null);
  const [savedSession]=useState(readPreviewSession);
  const restored=savedSession.session;
  const [storageError,setStorageError]=useState(savedSession.error);
  const [lineup,setLineup]=useState(()=>restored?.lineup || initialLineup());
  const lineupRef=useRef(lineup), pendingLineup=useRef(restored?.pending || null), history=useRef(restored?.history || []);
  const [activeKeys,setActiveKeys]=useState(()=>restored?.playback.fighters || lineupFighters(lineup));
  const [hudStocks,setHudStocks]=useState(()=>restored?.playback.stocks || [2,2]);
  const [phase,setPhase]=useState('entrance');
  const [awaitingStart,setAwaitingStart]=useState(restored?Boolean(restored.playback.awaitingStart):true);
  const [adjusting,setAdjusting]=useState(false);
  const [canUndo,setCanUndo]=useState(Boolean(restored?.history.length));
  const busy=useRef(false);
  const heldInput=useRef(null);
  const [chargingSide,setChargingSide]=useState(null);
  const [mobile, setMobile] = useState(() => window.matchMedia('(max-width: 680px)').matches);
  const view = mobile ? MOBILE_VIEW : VIEW;
  useEffect(() => {
    const query=window.matchMedia('(max-width: 680px)');
    const update=()=>setMobile(query.matches);
    query.addEventListener('change',update);
    return ()=>query.removeEventListener('change',update);
  }, []);
  const playback = useRef({ mode: 'entrance', started: performance.now() });
  const clock = useRef(resetAnimationClock(playback.current.started));
  const [assets, setAssets] = useState(null);
  const [error, setError] = useState('');
  const [ready, setReady] = useState(false);
  const [dropAvailable, setDropAvailable] = useState(false);
  const [status, setStatus] = useState('LOADING FIGHTERS');
  const [sound, setSound] = useState(restored?.sound ?? true);
  const [inspection, setInspection] = useState(false);
  const [inspectionFrame, setInspectionFrame] = useState(0);
  const [inspectionScene, setInspectionScene] = useState('entrance');
  const [inspectionPlaying, setInspectionPlaying] = useState(false);
  const inspectionCharge=inspectionScene.startsWith('charge-');
  const inspectionSide=Number(inspectionScene.split('-').at(-1));
  const inspectionMax = assets && inspectionScene!=='entrance'
    ? inspectionCharge ? (assets.manifest.fighters[activeKeys[inspectionSide]].move.charge?.frame || 0)+60
      : Math.max(240, Math.ceil(resultTiming(assets.manifest,inspectionSide,activeKeys,0,hudStocks[1-inspectionSide]===1).end*60)+180) : 240;
  const inspectionCursor = useRef(0);
  inspectionCursor.current = inspectionFrame;
  useEffect(() => {
    if (!inspection || !inspectionPlaying) return;
    let request, last = null, cursor = inspectionCursor.current;
    function tick(now) {
      if (last !== null && !document.hidden) cursor += Math.min(now-last, 50)*60/1000;
      last = now;
      const frame = Math.min(inspectionMax, Math.floor(cursor));
      setInspectionFrame(frame);
      if (frame === inspectionMax) setInspectionPlaying(false);
      else request = requestAnimationFrame(tick);
    }
    request = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(request);
  }, [inspection, inspectionPlaying, inspectionMax]);
  function seekInspection(frame) {
    setInspectionPlaying(false);
    setInspectionFrame(Math.max(0, Math.min(inspectionMax, frame)));
  }
  const audio = useRef(null);
  const played = useRef(new Set(restored?.playedSounds || []));
  const koProfile = useRef({ draws: [], intervals: [], last: null });
  const phaseProfile = useRef({ phase:null,draws:[],intervals:[],last:null });
  const [reduced, setReduced] = useState(() => restored?.reduced ?? window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    async function load() {
      const response = await fetch(`${BASE}manifest.json`, { signal: controller.signal });
      if (!response.ok) throw new Error('The character preview assets are unavailable.');
      const manifest = await response.json();
      const images = {};
      const clips = Object.values(manifest.environment);
      await Promise.all([...new Set(clips.flatMap(clipFiles))].map(async file => {
        const image = new Image(); image.src = `${BASE}${file}`; await image.decode(); images[file] = image;
      }));
      const soundData = {};
      await Promise.all(Object.entries(manifest.audio).map(async ([name, clip]) => {
        const response = await fetch(`${BASE}${clip.file}`, { signal: controller.signal });
        if (response.ok) soundData[name] = await response.arrayBuffer();
      }));
      if (active) {
        clock.current = resetAnimationClock(performance.now());
        playback.current = restored?restorePreviewPlayback(restored,clock.current.time):{ mode: 'entrance', started: clock.current.time, fighters:lineupFighters(lineupRef.current), stocks:lineupRef.current.players.map(p=>p.stocks),matchStart:true,awaitingStart:true };
        const tint = document.createElement('canvas'); tint.width = 512; tint.height = 384;
        const magnifier = document.createElement('canvas'); magnifier.width = magnifier.height = 256;
        const loaded={ manifest, images, tint, magnifier, soundData, fighterFiles:new Set(Object.values(manifest.fighters).flatMap(f=>Object.values(f.clips).flatMap(clipFiles))) };
        await loadFighterImages(loaded,[...playback.current.fighters,...(playback.current.nextFighters || [])]);
        if(active){setAssets(loaded);window.dispatchEvent(new Event('ironman:ready'));}
      }
    }
    load().catch(error => { if (active && error.name !== 'AbortError') setError(error.message); });
    return () => { active = false; controller.abort(); };
  }, []);
  function saveMatch() {
    setStorageError(writePreviewSession(capturePreviewSession({lineup:lineupRef.current,pending:pendingLineup.current,
      history:history.current,playback:playback.current,now:clock.current.time,playedSounds:played.current,sound,reduced})));
  }
  useEffect(()=>{
    if(!assets)return;
    saveMatch();
    function visibilityChanged() {
      if(document.hidden)cancelCharge();
      saveMatch();
      clock.current.real=performance.now();
      if(document.hidden)audio.current?.context.suspend().catch(()=>{});
      else if(sound && !reduced)audio.current?.context.resume().catch(()=>{});
    }
    const onPageHide=()=>saveMatch();
    const onBlur=()=>cancelCharge();
    document.addEventListener('visibilitychange',visibilityChanged);
    window.addEventListener('pagehide',onPageHide);
    window.addEventListener('blur',onBlur);
    return ()=>{document.removeEventListener('visibilitychange',visibilityChanged);window.removeEventListener('pagehide',onPageHide);window.removeEventListener('blur',onBlur);};
  },[assets,sound,reduced]);
  useEffect(() => {
    if (!assets) return;
    const ctx = canvas.current.getContext('2d');
    let request;
    function tick(now) {
      if(document.hidden) { clock.current.real=now; request=requestAnimationFrame(tick); return; }
      if (busy.current) { clock.current.real=now; request=requestAnimationFrame(tick); return; }
      // The title card covers the arena until the user starts. Avoid rendering
      // the frozen entrance effects behind it or consuming match time.
      if (!inspection && playback.current.awaitingStart) {
        clock.current.real=now; request=requestAnimationFrame(tick); return;
      }
      if (!inspection && !playback.current.awaitingStart) clock.current = advanceAnimationClock(clock.current, now);
      else clock.current.real=now;
      const inspectedState = inspectionScene === 'entrance' ? { mode: 'entrance', started: 0, fighters:activeKeys, stocks:hudStocks }
        : { mode: inspectionCharge?'charge':'result', winner: inspectionSide, started: 0, fighters:activeKeys, stocks:hudStocks,celebrate:hudStocks[1-inspectionSide]===1 };
      const drawStarted = import.meta.env.DEV ? performance.now() : 0;
      const result = draw(ctx, assets, inspection ? inspectedState : playback.current,
        inspection ? inspectionFrame*1000/60 : clock.current.time, inspection ? false : reduced, view);
      if (inspection) { setReady(false); setStatus(result.status); return; }
      if(result.chargeComplete)releaseCharge();
      if (import.meta.env.DEV) {
        const phase=result.ready?'ready':(result.next?.mode || playback.current.mode);
        const stats=phaseProfile.current;
        if(stats.phase!==phase && stats.draws.length) {
          const p95=values=>[...values].sort((a,b)=>a-b)[Math.min(values.length-1,Math.floor(values.length*.95))] || 0;
          console.debug('Animation phase profile',JSON.stringify({phase:stats.phase,fighters:playback.current.fighters,frames:stats.draws.length,
            drawP95ms:+p95(stats.draws).toFixed(2),intervalP95ms:+p95(stats.intervals).toFixed(2),framesOver34ms:stats.intervals.filter(ms=>ms>34).length}));
          phaseProfile.current={phase,draws:[],intervals:[],last:null};
        }
        const current=phaseProfile.current;current.phase=phase;
        if(current.draws.length<600) {
          current.draws.push(performance.now()-drawStarted);
          if(current.last!==null)current.intervals.push(now-current.last);
        }
        current.last=now;
        const profile=koProfile.current;
        if (result.ko && profile.draws.length<600) {
          profile.draws.push(performance.now()-drawStarted);
          if (profile.last!==null) profile.intervals.push(now-profile.last);
          profile.last=now;
        } else if (!result.ko && profile.draws.length) {
          const percentile=values=>[...values].sort((a,b)=>a-b)[Math.min(values.length-1,Math.floor(values.length*.95))] || 0;
          console.debug('KO playback profile',JSON.stringify({frames:profile.draws.length,
            drawP95ms:+percentile(profile.draws).toFixed(2),intervalP95ms:+percentile(profile.intervals).toFixed(2),
            framesOver34ms:profile.intervals.filter(ms=>ms>34).length}));
          koProfile.current={draws:[],intervals:[],last:null};
        }
      }
      if(pendingLineup.current && playback.current.mode==='result' &&
        result.stocks[1-playback.current.winner]<playback.current.stocks[1-playback.current.winner])setLineup(pendingLineup.current);
      if (result.next) {
        playback.current = result.next;
        // A taunt can straddle this transition. Retain its played cues so a
        // sound window crossing the boundary cannot trigger a second time.
        played.current=new Set(result.next.tauntStarted!==undefined
          ? [...played.current].filter(id=>id.startsWith('taunt-')) : []);
        setActiveKeys(result.next.fighters);retainFighterImages(assets,result.next.fighters);
        if(pendingLineup.current){lineupRef.current=withPlayedCharacters(pendingLineup.current);setLineup(lineupRef.current);pendingLineup.current=null;}
        saveMatch();
      }
      if(result.complete && pendingLineup.current){lineupRef.current=withPlayedCharacters(pendingLineup.current);setLineup(lineupRef.current);pendingLineup.current=null;saveMatch();}
      setHudStocks(previous=>previous.every((n,i)=>n===result.stocks[i])?previous:result.stocks);
      setPhase(result.complete?'complete':result.ready?'ready':playback.current.mode);
      if (sound && !reduced && audio.current?.context.state === 'running') {
        for (const cue of result.sounds) {
          const buffer = audio.current.buffers[cue.name];
          if (buffer && !played.current.has(cue.id)) {
            played.current.add(cue.id);
            const source = audio.current.context.createBufferSource();
            source.buffer = buffer; source.playbackRate.value=assets.manifest.audio[cue.name]?.playbackRate || 1; source.connect(audio.current.gain); source.start();
          }
        }
      }
      setReady(result.ready && !adjusting && lineupRef.current.champion===null);
      setDropAvailable(result.platforms.length>0 && !reduced);
      setStatus(result.status);
      request = requestAnimationFrame(tick);
    }
    request = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(request);
  }, [assets, reduced, sound, inspection, inspectionFrame, inspectionScene, view, activeKeys, adjusting]);
  useEffect(() => () => { audio.current?.context.close(); }, []);
  function unlockAudio() {
    if (!sound || reduced || !assets) return;
    if (!audio.current) {
      const context = new (window.AudioContext || window.webkitAudioContext)();
      const gain = context.createGain(); gain.gain.value = .5; gain.connect(context.destination);
      const engine = { context, gain, buffers: {} }; audio.current = engine;
      engine.ready=Promise.all(Object.entries(assets.soundData).map(([name,bytes])=>
        context.decodeAudioData(bytes.slice(0)).then(buffer=>{engine.buffers[name]=buffer;}).catch(()=>{})));
    }
    return Promise.all([audio.current.ready,audio.current.context.resume().catch(()=>{})]);
  }
  async function startMatch(){
    if(!assets || busy.current || !playback.current.awaitingStart)return;
    busy.current=true;setAdjusting(true);
    try{
      await unlockAudio();
      clock.current=resetAnimationClock(performance.now());
      playback.current={...playback.current,started:clock.current.time,awaitingStart:false};
      setAwaitingStart(false);played.current.clear();saveMatch();
    }finally{busy.current=false;setAdjusting(false);}
  }
  function dropFromPlatform() {
    if (!assets || busy.current || inspection) return;
    const released=releasePlatform(playback.current,clock.current.time,reduced);
    if (!released) return;
    playback.current=released;
    setDropAvailable(false);
    saveMatch();
  }
  async function setSituation(next, nextPhase='ready', saveUndo=true) {
    if(!assets || busy.current)return false;
    cancelCharge();
    next=withPlayedCharacters(next);
    busy.current=true;
    setAdjusting(true);setReady(false);setError('');
    try {
      await loadFighterImages(assets,lineupFighters(next));
      if(saveUndo){history.current.push(lineupRef.current);setCanUndo(true);}
      lineupRef.current=next;pendingLineup.current=null;setLineup(next);
      const fighters=lineupFighters(next);setActiveKeys(fighters);setHudStocks(next.players.map(p=>p.stocks));
      clock.current=resetAnimationClock(performance.now());played.current.clear();
      playback.current={mode:'entrance',started:clock.current.time-(nextPhase==='ready'?3000:0),fighters,stocks:next.players.map(p=>p.stocks)};
      setAwaitingStart(false);
      retainFighterImages(assets,fighters);
      saveMatch();
      return true;
    }catch(e){setError(e.message);return false;}finally{busy.current=false;setAdjusting(false);}
  }
  function replay() {unlockAudio();setSituation(lineupRef.current,'entrance',false);}
  function beginCharge(side,input) {
    if(!ready || inspection || busy.current || heldInput.current || playback.current.mode==='charge')return false;
    if(!assets.manifest.fighters[activeKeys[side]].move.charge)return false;
    unlockAudio();heldInput.current=input;setChargingSide(side);setReady(false);
    clock.current=advanceAnimationClock(clock.current,performance.now());played.current.clear();
    playback.current={mode:'charge',winner:side,started:clock.current.time,fighters:activeKeys,
      stocks:lineupRef.current.players.map(p=>p.stocks)};
    return true;
  }
  function cancelCharge() {
    if(playback.current.mode!=='charge')return;
    heldInput.current=null;setChargingSide(null);
    playback.current={mode:'entrance',started:clock.current.time-3000,fighters:playback.current.fighters,stocks:lineupRef.current.players.map(p=>p.stocks)};
    played.current.clear();setReady(true);saveMatch();
  }
  function releaseCharge() {
    if(playback.current.mode!=='charge' || busy.current)return;
    clock.current=advanceAnimationClock(clock.current,performance.now());
    const charge=chargeProgress(playback.current,clock.current.time,assets.manifest);
    heldInput.current=null;setChargingSide(null);
    win(playback.current.winner,charge);
  }
  async function win(winner,charge=null) {
    if ((!ready && !(charge && playback.current.mode==='charge')) || inspection || busy.current || playback.current.mode === 'result') return;
    busy.current=true;
    setReady(false);setAdjusting(true);setError('');unlockAudio();
    const before=lineupRef.current,next=takeStock(before,winner);
    try {
      const fighters=lineupFighters(before), nextFighters=lineupFighters(next).map((key,i)=>key || fighters[i]);
      history.current.push(before);setCanUndo(true);pendingLineup.current=next;
      if(!charge)played.current.clear();clock.current=resetAnimationClock(performance.now());
      playback.current={mode:'result',winner,started:clock.current.time-(charge?.sourceTime || 0)*1000,fighters,nextFighters,
        chargeFrames:charge?.frames || 0,celebrate:before.players[1-winner].stocks===1,
        stocks:before.players.map(p=>p.stocks),nextStocks:next.players.map(p=>p.stocks),finishedRun:next.champion!==null};
      saveMatch();
      await loadFighterImages(assets,[...fighters,...nextFighters]);
      clock.current=resetAnimationClock(performance.now());playback.current.started=clock.current.time-(charge?.sourceTime || 0)*1000;
    }catch(e){
      history.current.pop();pendingLineup.current=null;
      playback.current={mode:'entrance',started:clock.current.time-3000,fighters:lineupFighters(before),stocks:before.players.map(p=>p.stocks)};
      setCanUndo(history.current.length>0);saveMatch();setError(e.message);return false;
    }finally{busy.current=false;setAdjusting(false);}
  }
  async function undo() {
    const previous=history.current.at(-1);
    if(previous && await setSituation(previous,'ready',false)){history.current.pop();saveMatch();}
    setCanUndo(history.current.length>0);
  }
  async function startOver() {
    if(!assets || busy.current)return;
    busy.current=true;setAdjusting(true);setReady(false);setError('');
    heldInput.current=null;setChargingSide(null);
    try {
      const fresh=freshPreviewSession(window.matchMedia('(prefers-reduced-motion: reduce)').matches);
      await loadFighterImages(assets,fresh.playback.fighters);
      lineupRef.current=fresh.lineup;pendingLineup.current=null;history.current=[];
      clock.current=resetAnimationClock(performance.now());
      playback.current=restorePreviewPlayback(fresh,clock.current.time);played.current.clear();
      setAwaitingStart(true);
      setLineup(fresh.lineup);setActiveKeys(fresh.playback.fighters);setHudStocks([2,2]);
      setCanUndo(false);setPhase('entrance');setStatus('');
      setInspection(false);setInspectionPlaying(false);setInspectionScene('entrance');setInspectionFrame(0);
      if(inspector.current)inspector.current.open=false;
      if(devTools.current)devTools.current.open=false;
      // Close any currently playing announcer/effect before the new entrance.
      audio.current?.context.close().catch(()=>{});audio.current=null;
      setSound(fresh.sound);setReduced(fresh.reduced);
      phaseProfile.current={phase:null,draws:[],intervals:[],last:null};
      koProfile.current={draws:[],intervals:[],last:null};
      retainFighterImages(assets,fresh.playback.fighters);
      setStorageError(writePreviewSession(fresh));
    } catch(e) {setError(e.message);} finally {busy.current=false;setAdjusting(false);}
  }
  function chooseSide(side,value) {
    const [index,stocks]=value.split(':').map(Number);
    const next={...lineupRef.current,players:lineupRef.current.players.map(p=>({index:Math.min(p.index,CHARACTER_ROSTER.length-1),stocks:Math.max(1,p.stocks)})),champion:null};
    next.players[side]={index:side===0?index:CHARACTER_ROSTER.length-1-index,stocks};
    setSituation(next,'ready');
  }
  const names=activeKeys.map(key=>assets?.manifest.fighters[key]?.name || CHARACTER_ROSTER.find(c=>key.startsWith(c.slug))?.name || 'Fighter');
  return <main className="animation-preview">
    <header className="preview-header">
      <h1>Iron Man SSBM</h1>
      {import.meta.env.DEV && <details ref={devTools} className="dev-tools" onToggle={event=>{
        if(event.target!==event.currentTarget)return;
        if(!event.currentTarget.open) {
          setInspectionPlaying(false);
          if(inspector.current)inspector.current.open=false;
        }
      }}>
        <summary aria-label="More developer tools">More</summary>
        <div className="dev-tools-panel" aria-label="Developer tools">
          <p className="dev-tools-label">Development tools</p>
    <div className="preview-controls">
      <button className="preview-replay" disabled={!assets || inspection || adjusting || lineup.champion!==null} onClick={replay}>↻ Replay entrance</button>
    </div>
    <details className="preview-adjustments" open><summary>Adjust current phase</summary>
      <div className="preview-adjustment-fields">
        <label>Current phase<select value={phase==='respawn'?'entrance':phase} disabled={!assets || adjusting || inspection} onChange={event=>setSituation({...lineupRef.current,champion:null,players:lineupRef.current.players.map(p=>({index:Math.min(p.index,CHARACTER_ROSTER.length-1),stocks:Math.max(1,p.stocks)}))},event.target.value)}>
          <option value="ready">Ready — on stage</option><option value="entrance">Respawn and drop</option><option value="result" disabled>KO in progress</option><option value="complete" disabled>Iron Man complete</option>
        </select></label>
        {[0,1].map(side=>{
          const current=CHARACTER_ROSTER.findIndex(c=>activeKeys[side]===c.slug+(side?'-left':''));
          return <label key={side}>{side===0?'Left side':'Right side'}<select aria-label={side===0?'Left character and stocks':'Right character and stocks'} value={`${current}:${hudStocks[side]}`} disabled={!assets || adjusting || inspection} onChange={event=>chooseSide(side,event.target.value)}>
            {hudStocks[side]===0 && <option value={`${current}:0`} disabled>{names[side]} — 0 stocks</option>}
            {CHARACTER_ROSTER.flatMap((character,index)=>[2,1].map(stocks=><option key={`${index}:${stocks}`} value={`${index}:${stocks}`} disabled={assets?.manifest.fighters[character.slug+(side?'-left':'')]?.facing!==(side?'left':'right')}>{character.name} — {stocks} {stocks===1?'stock':'stocks'}{assets && assets.manifest.fighters[character.slug+(side?'-left':'')]?.facing!==(side?'left':'right')?' (preparing)':''}</option>))}
          </select></label>;
        })}
        <button disabled={!assets || !canUndo || adjusting || inspection} onClick={undo}>Undo last change</button>
      </div>
    </details>
    <details ref={inspector} className="preview-inspector" onToggle={event => {
      if(event.currentTarget.open)cancelCharge();
      setInspection(event.currentTarget.open);
      setInspectionPlaying(false);
      if (!event.currentTarget.open) clock.current.real=performance.now();
    }}>
      <summary>Inspect animation frames</summary>
      <div><label>Sequence <select value={inspectionScene} onChange={event => {
        setInspectionScene(event.target.value); seekInspection(0);
      }}><option value="entrance">Drop and landing</option><option value="0">{names[0]} wins</option><option value="1">{names[1]} wins</option>
        {[0,1].map(side=>assets?.manifest.fighters[activeKeys[side]].move.charge && <option key={side} value={`charge-${side}`}>{names[side]} charges</option>)}</select></label>
        <label>Frame {inspectionFrame} <input aria-label="Animation frame" type="range" min="0" max={inspectionMax} step="1"
          value={inspectionFrame} onChange={event => seekInspection(Number(event.target.value))} /></label>
        <div className="preview-frame-controls" role="group" aria-label="Animation playback">
          <button aria-label="Previous frame" disabled={!assets || inspectionFrame===0} onClick={()=>seekInspection(inspectionFrame-1)}>← Frame</button>
          <button aria-label={inspectionPlaying?'Pause animation':'Play animation'} disabled={!assets} onClick={()=>{
            if (!inspectionPlaying && inspectionFrame===inspectionMax) setInspectionFrame(0);
            setInspectionPlaying(playing=>!playing);
          }}>{inspectionPlaying?'Ⅱ Pause':'▶ Play'}</button>
          <button aria-label="Next frame" disabled={!assets || inspectionFrame===inspectionMax} onClick={()=>seekInspection(inspectionFrame+1)}>Frame →</button>
        </div>
      </div>
    </details>
        </div>
      </details>}
    </header>
    <section className={`preview-arena${awaitingStart && !inspection?' awaiting-start':''}`} aria-label={awaitingStart && !inspection?'Start a new Iron Man match':'Character animation demonstration'}
      onContextMenu={event=>event.preventDefault()} onDragStart={event=>event.preventDefault()}>
      <div className="preview-status" role="status">{!adjusting && status==='READY'?'READY':''}</div>
      <canvas ref={canvas} width={view.width} height={view.height} role="img" aria-label={phase==='complete'?'Game! Match complete.':`${names[0]} on the left and ${names[1]} on the right, with respawn, idle, and victory animations.`} />
      {matchupHomes(assets?.manifest,activeKeys).map((home, side) => {
        const target=fighterTarget(view,home,assets?.manifest,activeKeys);
        return <button key={side} className="preview-fighter-target" disabled={!ready && chargingSide!==side}
          aria-label={`Choose ${names[side]} as winner`}
          style={Object.fromEntries(Object.entries(target).map(([key,value])=>[key,`${value}%`]))}
          onPointerDown={event=>{
            if(event.button!==0)return;
            if(beginCharge(side,`pointer-${event.pointerId}`)){
              event.preventDefault();
              event.currentTarget.setPointerCapture(event.pointerId);
            }
          }}
          onPointerUp={event=>{if(heldInput.current===`pointer-${event.pointerId}`)releaseCharge();}}
          onPointerCancel={event=>{if(heldInput.current===`pointer-${event.pointerId}`)cancelCharge();}}
          onLostPointerCapture={event=>{if(heldInput.current===`pointer-${event.pointerId}`)cancelCharge();}}
          onContextMenu={event=>event.preventDefault()}
          onKeyDown={event=>{if([' ','Enter'].includes(event.key)){event.preventDefault();if(!event.repeat)beginCharge(side,`key-${event.key}`);}}}
          onKeyUp={event=>{if(heldInput.current===`key-${event.key}`){event.preventDefault();releaseCharge();}}}
          onBlur={()=>{if(heldInput.current?.startsWith('key-'))cancelCharge();}}
          onClick={event=>{if(!heldInput.current && (event.detail===0 || !assets?.manifest.fighters[activeKeys[side]].move.charge))win(side);}} />;
      })}
      {dropAvailable && !awaitingStart && !inspection && !adjusting && <button
        className="preview-drop-target" aria-label="Drop from platform now" onClick={dropFromPlatform} />}
      {!assets && !awaitingStart && <div className="preview-loading">{error || 'Preparing the fighters…'}</div>}
      {awaitingStart && !inspection && <div className="match-title-card">
        <img className="match-title-symbol" src={`${BASE}title-symbol.webp`} alt="" draggable="false" />
        <div className="match-title-content">
          <div className="match-title-art" role="img" aria-label="Super Smash Bros. Melee">
            <img className="match-title-logo" src={`${BASE}title-logo.webp`} alt="" draggable="false" width="448" height="128" />
            <img className="match-title-melee" src={`${BASE}title-melee.webp`} alt="" draggable="false" width="176" height="40" />
          </div>
          <p className="match-title-mode">Iron Man</p>
          <button className="match-start" disabled={!assets || adjusting} onClick={startMatch}>{!assets?'Preparing fighters…':'Start match'}</button>
        </div>
      </div>}
      <div className="preview-stock-counts" aria-live="polite">{names.map((name,side)=><span key={side}>{name}: {hudStocks[side]} {hudStocks[side]===1?'stock':'stocks'}</span>)}</div>
      <div className="preview-ports"><span><i />P1 / {names[0]}</span><span>P2 / {names[1]}<i /></span></div>
    </section>
    <p className="match-helper" style={{visibility:awaitingStart?'hidden':'visible'}}>Tap stock winner</p>
    <MatchStats lineup={lineup} assets={assets} />
    {error && <p role="alert">{error}</p>}
    {storageError && <p role="alert">{storageError}</p>}
    <div className="match-actions">
      <button className="start-over" disabled={!assets || adjusting} onClick={startOver}>Start Over</button>
    </div>
      <footer className="preview-footer">
      <div className="preview-preferences">
      <label><input type="checkbox" checked={sound} onChange={event => {
        setSound(event.target.checked);
        if (audio.current) audio.current.gain.gain.value = event.target.checked ? .5 : 0;
      }} /> Sound</label>
      <label><input type="checkbox" checked={reduced} onChange={event => setReduced(event.target.checked)} /> Reduce motion</label>
      </div>
      <p>Original Melee models, animations, effects, and sounds.</p>
    </footer>
  </main>;
}
