import { fighterScale } from './fighterScale.js';
import { companionKey, companionPosition, NANA_INPUT_DELAY, PARTNER_SEPARATION, PARTNER_CONTACT_SEPARATION } from './previewCompanions.js';
import { composeView, launchPosition } from './previewCamera.js';
import { DEFAULT_HOME, matchupSpacing } from './combatSpacing.js';
import {chargeProgress,chargedHitbox} from './smashInteraction.js';
export const FLOOR = 456;
export const SPAWN_Y = 150;
export const HOME = DEFAULT_HOME;
export const FIGHTERS = ['dr-mario', 'roy-left'];
const clamp = x => Math.max(0, Math.min(1, x));
export const LAUNCH_TIME = .9;
export const ENTRANCE_HOLD = 1.05;
export const FALL_TIME = .5;
// Shorten only the platform wait, leaving the shared clock and any overlapping
// survivor taunt untouched. A second tap after release has no effect.
export function releasePlatform(state, now, reduced = false) {
  if (reduced || state.awaitingStart || !['entrance', 'respawn'].includes(state.mode)) return null;
  const elapsed = Math.max(0, (now-state.started)/1000);
  if (elapsed >= (state.platformHoldSeconds ?? ENTRANCE_HOLD)) return null;
  return {...state, platformHoldSeconds: elapsed};
}
// Requested preview pacing: retain the original cycle, halve its duration.
export const POST_DROP_DURATION_SCALE = .5;
// Particle exports have 5 px/game-unit, versus 17.28 world px/game-unit
// for the fighters. Contact bursts must use the same projection as body sparks.
export const PARTICLE_SCALE = 3.456;
export const IMPACT_PARTICLE_SCALE = PARTICLE_SCALE;
// Same projection as render_preview.py: 512 px / 4.8 m, 0.1 m per game
// unit, then the canvas fighter scale. Vertical motion includes camera pitch.
const FIGHTER_UNIT_SCALE = 512/4.8 * .1 * 1.62;
const CAMERA_VERTICAL_SCALE = 10/Math.hypot(10, 1.2);

export function damageModelOffset(manifest, seconds, hitlag, electric, facing) {
  const data = manifest.common.damageModelShift;
  const frame = Math.floor((seconds+1e-9)*data.fps);
  const duration = Math.trunc(data.durationMultiplier*hitlag*60 + data.durationBase);
  if (frame < 0 || frame >= duration) return [0, 0];
  // This preview starts both victims on a flat floor; electric overrides ground.
  const table = data.tables[electric ? 'electric' : 'ground'];
  const [x, y] = table[frame%table.length];
  return [x*facing*FIGHTER_UNIT_SCALE, -y*FIGHTER_UNIT_SCALE*CAMERA_VERTICAL_SCALE];
}

export function resultTiming(manifest, winner, fighters=FIGHTERS, chargeFrames=0, celebrate=false) {
  const fighter = manifest.fighters[fighters[winner]], params=manifest.common.hitlag;
  const fallback=fighter.move.hitboxes.find(h=>h.ID===fighter.move.selectedHitbox);
  const spacedContact=matchupSpacing(manifest,fighters).contacts[winner];
  let accumulated=0;
  const hits=(fighter.move.hitPhases || [{frame:fighter.move.activeStart,hitbox:fallback}]).map((source,index)=>{
    const phase=index===0 && spacedContact?{...source,frame:spacedContact.frame}:source;
    // Link's second action resets smash attributes in the original engine.
    const hit=chargedHitbox(phase.hitbox,fighter.move.charge,
      phase.frame<(fighter.move.sequence?.[1]?.start ?? Infinity)?chargeFrames:0);
    const hitlag=Math.min(params.maximum,Math.trunc(Math.trunc(hit.Damage*params.damageMultiplier+params.base)*(hit.Element===2?params.electricMultiplier:1)))/60;
    const result={...phase,hitbox:hit,at:phase.frame/60+accumulated,hitlag};
    accumulated+=hitlag;return result;
  });
  const leaderHits=[...hits], leaderAttackEnd=fighter.clips.smash.duration+accumulated;
  const partnerKey=companionKey(fighters[winner]),partner=manifest.fighters[partnerKey];
  let companionHits=[],companionAttackEnd=0;
  if(partner) {
    const contact=matchupSpacing(manifest,fighters.map((key,side)=>side===winner?partnerKey:key)).contacts[winner];
    const phase=partner.move.hitPhases[0],hitbox=chargedHitbox(phase.hitbox,partner.move.charge,chargeFrames);
    const frame=contact?.frame ?? phase.frame;
    const hitlag=Math.min(params.maximum,Math.trunc(Math.trunc(hitbox.Damage*params.damageMultiplier+params.base)*(hitbox.Element===2?params.electricMultiplier:1)))/60;
    companionHits=[{frame,hitbox,at:frame/60,hitlag,companion:true}];
    hits.push({...companionHits[0],at:frame/60+NANA_INPUT_DELAY});
    hits.sort((a,b)=>a.at-b.at);
    companionAttackEnd=NANA_INPUT_DELAY+partner.clips.smash.duration+hitlag;
  }
  const final=hits.at(-1),hitAt=final.at,hitlag=final.hitlag;
  const attackEnd=Math.max(leaderAttackEnd,companionAttackEnd),koAt=hitAt+hitlag+LAUNCH_TIME;
  const ko=manifest.environment[`ko-p${2-winner}`];
  const koParticles=manifest.environment['ko-particles'];
  const koDuration=Math.max(ko.frames/ko.fps,koParticles?koParticles.frames/koParticles.fps:0);
  const tauntAt=attackEnd,tauntEnd=celebrate&&fighter.clips.taunt?tauntAt+fighter.clips.taunt.duration:0;
  return {hits,leaderHits,companionHits,leaderAttackEnd,companionAttackEnd,hitAt,hitlag,attackEnd,koAt,tauntAt,tauntEnd,
    end:Math.max(attackEnd+.2,koAt+koDuration)};
}

export function moveTime(t,hits) {
  let elapsed=0;
  for(const hit of hits) {
    if(t<hit.at)break;
    if(t<hit.at+hit.hitlag)return hit.frame/60;
    elapsed+=hit.hitlag;
  }
  return t-elapsed;
}

export function eventTime(frame,hits) {
  return frame/60+hits.filter(hit=>hit.frame<frame).reduce((sum,hit)=>sum+hit.hitlag,0);
}

export function overlayAt(clip, seconds) {
  return clip.rgba[Math.floor(Math.max(0, seconds) * clip.fps) % clip.rgba.length];
}

function applyTaunt(frame,state,t,manifest,timing) {
  const fighter=manifest.fighters[state.fighters[state.winner]],clip=fighter.clips.taunt;
  if(!clip || t<timing.tauntAt)return;
  const age=t-timing.tauntAt,p=frame.positions[state.winner];
  p.clip=age<clip.duration?'taunt':'idle';p.time=age<clip.duration?age:age-clip.duration;p.loop=age>=clip.duration;
  delete p.companionMotion;
  const data=fighter.taunt;
  for(const [i,e] of (data?.events || []).entries()) {
    const elapsed=age-e.frame/60;
    if(elapsed<0)continue;
    const sound=e.opcode===17?e.fields['SFX ID']:e.name==='Pseudo Random Sound Effect'?e.fields['SFX ID 1']:null;
    if(sound!==null && elapsed<.12)frame.sounds.push({id:`taunt-${i}`,name:`sound-${sound}`});
    const overlay=data.overlays?.[e.fields.ID];
    if(e.name==='Color Animation' && overlay && elapsed<e.fields.Duration/60)p.overlay=overlayAt(overlay,elapsed);
    if(e.opcode!==10)continue;
    const kind=manifest.effectMap?.[e.fields['GFX ID']],effect=manifest.environment[kind];
    if(!effect || elapsed>=effect.frames/effect.fps)continue;
    const anchor=data.attachments?.[Math.min(Math.floor(age*data.fps),data.attachments.length-1)]?.[e.fields['GFX ID']];
    if(!anchor)continue;
    const origin=clip.anchor || fighter.anchor || [256,330],scale=1.62*fighterScale({...fighter,scale:clip.exportScale ?? fighter.scale});
    frame.effects.push({kind,age:elapsed,x:p.x+(anchor[0]-origin[0])*scale,y:p.y+(anchor[1]-origin[1])*scale,
      sign:(state.winner===0?1:-1)*(e.fields['GFX ID']===1024?-1:1),scale:effect.pixelsPerGameUnit?FIGHTER_UNIT_SCALE/effect.pixelsPerGameUnit:1.4});
  }
}

// Camera easing and knockback path are presentation choreography. Move commands,
// hitstop parameters, color cycles and effect clips come from the disc.
export function previewFrame(state, now, manifest, reduced = false, view) {
  const timing=state.mode==='result'?resultTiming(manifest,state.winner,state.fighters,state.chargeFrames,state.celebrate):null;
  const ending=manifest.environment['game-end'];
  const gameAt=reduced ? .6 : (timing?.koAt || 0);
  const elapsed=Math.max(0,(now-state.started)/1000);
  const complete=Boolean(state.finishedRun && timing && elapsed+1e-9>=gameAt);
  // Hold the match and camera framing at the final KO. The blast, stock-loss
  // treatment, camera quake and Game! HUD keep their independent effect clocks.
  const sceneNow=state.awaitingStart?state.started:complete?state.started+(reduced?gameAt-.001:gameAt)*1000:now;
  const frame=worldFrame(complete?{...state,finishedRun:false,celebrate:false}:state,sceneNow,manifest,reduced);
  const gameAge=Math.max(0,elapsed-gameAt);
  if(complete) {
    if(frame.ko)frame.ko.age=gameAge;
    if(frame.stockLoss)frame.stockLoss.age=gameAge;
    // The match is already decided; finish the requested celebration under
    // Game! without moving the held base camera or restarting the explosion.
    if(state.celebrate && !reduced)applyTaunt(frame,state,elapsed,manifest,timing);
  }
  const active=frame.next || state;
  const composed=composeView(frame,active,Math.max(0,(sceneNow-active.started)/1000),manifest,
    active.mode==='result'?timing:null,reduced,view);
  if(complete) {
    composed.complete=true;
    composed.status='';
    composed.ready=false;
    composed.gameEnd={age:reduced?1:gameAge};
    // Keep this cue pending until decoded/unlocked; the player deduplicates it.
    if(gameAge>=(ending?.announcerDelayFrames ?? 8)/60)
      composed.sounds.push({id:'game-announcer',name:'game-announcer'});
  }
  if(state.awaitingStart){composed.ready=false;composed.status='';composed.sounds=[];}
  else if(state.mode==='entrance' && state.matchStart){
    const go=manifest.environment['game-go'],age=elapsed-(reduced?0:(state.platformHoldSeconds ?? ENTRANCE_HOLD));
    if(go && age>=0 && age<go.frames/go.fps){
      composed.gameGo={age:reduced?10/60:age};composed.status='';
      if(age>=go.announcerDelayFrames/go.fps)composed.sounds.push({id:'go-announcer',name:'go-announcer'});
    }
  }
  return composed;
}

function worldFrame(state, now, manifest, reduced = false) {
  const t = Math.max(0, (now - state.started) / 1000) + 1e-9;
  const fighters=state.fighters || FIGHTERS;
  if(state.mode==='charge') {
    const progress=chargeProgress(state,now,manifest);
    const frame=worldFrame({...state,mode:'result'},state.started+progress.sourceTime*1000,manifest,false);
    // Bone motion stops, but already-emitted windup particles keep aging.
    frame.effects=frame.effects.map(effect=>({...effect,age:effect.age+progress.held}))
      .filter(effect=>effect.age<manifest.environment[effect.kind].frames/manifest.environment[effect.kind].fps);
    frame.ready=false;frame.status='';frame.chargeComplete=progress.complete;
    if(progress.charging && !reduced) {
      const data=manifest.common.smashCharge,p=frame.positions[state.winner],sign=state.winner===0?1:-1;
      p.overlay=overlayAt(data.overlay,progress.held);
      const shift=data.shake[Math.floor(progress.held*60)%data.shake.length];
      p.modelOffset=[shift[0]*sign*FIGHTER_UNIT_SCALE,-shift[1]*FIGHTER_UNIT_SCALE*CAMERA_VERTICAL_SCALE];
      for(const e of data.overlay.effects) {
        const age=progress.held-e.frame/60,clip=manifest.environment['charge-dust'];
        if(age>=0 && age<clip.frames/clip.fps)frame.effects.push({kind:'charge-dust',age,x:p.x,y:p.y,sign,scale:PARTICLE_SCALE});
      }
      if(progress.held*60>=data.soundDelayFrames)frame.sounds.push({id:'smash-charge',name:`sound-${data.soundId}`});
    }
    const p=frame.positions[state.winner],partner=manifest.fighters[companionKey(p.fighter)];
    if(partner && p.companionMotion) {
      const time=Math.max(0,(now-state.started)/1000-NANA_INPUT_DELAY),holdAt=partner.move.charge.frame/60;
      p.companionMotion={...p.companionMotion,clip:time>0?'smash':'idle',loop:time===0,time:Math.min(time,holdAt),
        overlay:time>=holdAt&&!reduced?overlayAt(manifest.common.smashCharge.overlay,time-holdAt):undefined};
    }
    return frame;
  }
  const idleSince = state.idleSince || [state.started, state.started];
  const spacing=matchupSpacing(manifest,fighters), homes=spacing.homes;
  const positions = homes.map((x, side) => ({ x, y: FLOOR, clip: 'idle', fighter:fighters[side],
    time: (now - idleSince[side]) / 1000, loop: true, alpha: 1 }));
  const frame = { positions, platforms: [], effects: [], sounds: [], ready: false,
    stocks:state.stocks || [2,2], status: 'ON DECK', impact: null, magnifier: null, ko: null };
  if (state.mode === 'result') {
    const winner = state.winner, loser = 1-winner, sign = winner === 0 ? 1 : -1;
    const timing=resultTiming(manifest, winner, fighters,state.chargeFrames,state.celebrate);
    const { hits, leaderHits, companionHits, leaderAttackEnd, companionAttackEnd, hitAt, hitlag, attackEnd, koAt, tauntEnd, end: fullEnd } = timing;
    const end = reduced ? .6 : fullEnd;
    if (t >= end) {
      const next = { mode: 'respawn', winner, fighters:state.nextFighters || fighters, stocks:state.nextStocks || state.stocks, started: state.started + end*1000, idleSince: [...idleSince] };
      next.arrivals=[false,false];
      next.arrivals[loser]=next.fighters[loser]!==fighters[loser];
      next.idleSince[winner] = state.started + (reduced ? 0 : Math.max(attackEnd,tauntEnd))*1000;
      next.idleSince[loser] = next.started;
      // The survivor's celebration has its own clock; it never holds up the
      // next fighter's platform, drop, landing, or availability for input.
      if(state.celebrate && !reduced && tauntEnd>end)
        next.tauntStarted=state.started+timing.tauntAt*1000;
      return { ...worldFrame(next, now, manifest, reduced), next };
    }
    frame.status = `${manifest.fighters[fighters[winner]].name.toUpperCase()} WINS`;
    const win = positions[winner], lose = positions[loser];
    if (reduced) { lose.alpha = 0; frame.stocks=[...frame.stocks]; frame.stocks[loser]=Math.max(0,frame.stocks[loser]-1); return frame; }
    const attackTime = moveTime(t,leaderHits);
    const contactDistance=(spacing.contacts[winner]?.distance ?? 17)*FIGHTER_UNIT_SCALE
      -(companionHits.length?PARTNER_CONTACT_SEPARATION:0);
    const step=Math.max(0,homes[1]-homes[0]-contactDistance);
    const approach = time => sign*step*clamp(time/Math.min(.18,hits[0].at))*(1-clamp((time-attackEnd)/.2));
    win.x += approach(t);
    if(state.nextFighters && t>=koAt) {
      const destination=matchupSpacing(manifest,state.nextFighters).homes[winner];
      const p=clamp((t-koAt-.15)/.65);win.x+=(destination-homes[winner])*p*p*(3-2*p);
    }
    // Freeze the return's starting view at KO, even if attack recovery continues.
    frame.cameraWinner = { x:homes[winner]+approach(Math.min(t,koAt)), y:FLOOR };
    win.clip = t < leaderAttackEnd ? 'smash' : 'idle'; win.loop = t >= leaderAttackEnd;
    win.time = t < leaderAttackEnd ? attackTime : t-leaderAttackEnd;
    const fighter = manifest.fighters[fighters[winner]];
    for (const event of fighter.move.events) {
      const wallAt = eventTime(event.frame,leaderHits);
      const age = t-wallAt+(event.frame<=fighter.move.charge?.frame?(state.chargeFrames || 0)/60:0);
      if (event.opcode === 10 && age >= 0) {
        const id = event.fields['GFX ID'];
        const kind = manifest.effectMap?.[id] || ({1011:'smash-flash',1016:'dust',1042:'hand-electric',1059:'smash-ground'})[id];
        const clip = kind && manifest.environment[kind];
        if (clip && age < clip.frames/clip.fps) {
          const anchoredTime=kind==='hand-fire'?event.frame/60:attackTime;
          const effectX=kind==='hand-fire'?homes[winner]+approach(wallAt):win.x;
          const anchors = fighter.move.attachments[Math.min(Math.floor(anchoredTime*60), fighter.move.attachments.length-1)];
          const anchor = anchors[String(id)], origin=fighter.anchor || [256,330], scale=1.62*fighterScale(fighter);
          frame.effects.push({ kind, age, afterFighter: ['hand-electric','hand-fire','smash-flash'].includes(kind) ? winner : undefined,
            x: effectX+(anchor[0]-origin[0])*scale,
            y: win.y+(anchor[1]-origin[1])*scale, sign,
            scale: kind === 'dust' || kind === 'smash-ground' ? 1.4 : PARTICLE_SCALE });
        }
      }
      if (event.opcode === 17 || event.opcode === 18) {
        const isVoice = event.opcode === 18 || event.fields['Behavior'] === 2;
        const sourceSound = event.opcode === 17 ? `sound-${event.fields['SFX ID']}` : null;
        if (age >= 0 && age < .12) frame.sounds.push({ id: `move-${event.opcode}-${event.frame}-${event.fields['SFX ID'] ?? 'voice'}`,
          name: manifest.audio?.[sourceSound] ? sourceSound : `${fighters[winner].replace(/-left$/, '')}-${isVoice ? 'voice' : 'swing'}` });
      }
    }
    if(companionHits.length) {
      const local=Math.max(0,t-NANA_INPUT_DELAY),contact=companionHits[0];
      const winding=t>=NANA_INPUT_DELAY && t<companionAttackEnd;
      const recovery=clamp((t-companionAttackEnd+.15)/.15);
      const advance=clamp(local/(contact.frame/60))*(1-recovery);
      win.companionMotion={clip:winding?'smash':'idle',loop:!winding,
        time:winding?moveTime(local,companionHits):Math.max(0,t-companionAttackEnd),
        x:win.x-sign*(PARTNER_SEPARATION-(PARTNER_SEPARATION-PARTNER_CONTACT_SEPARATION)*advance)};
    }
    const partner=companionPosition(win,winner,manifest);
    if(partner && t<companionAttackEnd) {
      const source=manifest.fighters[partner.fighter];
      for(const event of source.move.events.filter(e=>e.opcode===10)) {
        const age=t-NANA_INPUT_DELAY-eventTime(event.frame,companionHits)+(event.frame<=source.move.charge?.frame?(state.chargeFrames || 0)/60:0);
        const id=event.fields['GFX ID'],kind=manifest.effectMap?.[id],clip=manifest.environment[kind];
        if(!clip || age<0 || age>=clip.frames/clip.fps)continue;
        const anchors=source.move.attachments[Math.min(Math.floor(partner.time*60+1e-7),source.move.attachments.length-1)];
        const anchor=anchors[String(id)],origin=source.anchor || [256,330],scale=1.62*fighterScale(source);
        if(!anchor)continue;
        frame.effects.push({kind,age,afterCompanion:kind==='smash-flash'?winner:undefined,
          x:partner.x+(anchor[0]-origin[0])*scale,y:partner.y+(anchor[1]-origin[1])*scale,sign,
          scale:kind==='dust' || kind==='smash-ground'?1.4:PARTICLE_SCALE});
      }
    }
    const contact=hits.findLast(hit=>t>=hit.at);
    const sinceHit = contact ? t-contact.at : -1;
    if (sinceHit >= 0) {
      const flight = Math.max(0, t-hitAt-hitlag), p = clamp(flight/LAUNCH_TIME);
      const element=contact.hitbox.Element, electric=element===2;
      const damageOverlay = electric ? manifest.common.electricDamageOverlay : element===1 ? manifest.common.fireDamageOverlay : element===13 ? manifest.common.darkDamageOverlay : manifest.common.normalDamageOverlay;
      // Standard middle-body launch: hold DamageFlyN frame zero during
      // hitlag, then advance that same source animation as knockback starts.
      // DamageFlyRoll is a separate percent/RNG-dependent reaction, not the
      // second half of every launch (ftCo_8008DCE0). Do not splice it in.
      lose.clip = t<hitAt && !companionHits.length ? 'recoil' : 'hit';
      const recoilTime=1/manifest.fighters[fighters[loser]].clips.recoil.fps+
        Math.max(0,sinceHit-contact.hitlag);
      lose.time = lose.clip==='recoil'?recoilTime:flight;
      // Melee keeps the damage pose held but moves its rendered model using
      // the disc's damage-shift cycle. This must not move the physics position.
      lose.modelOffset = damageModelOffset(manifest, sinceHit, contact.hitlag, electric, -sign);
      if (damageOverlay && sinceHit < damageOverlay.rgba.length/60) {
        lose.overlay = overlayAt(damageOverlay, sinceHit);
      }
      lose.loop = false;
      Object.assign(lose,launchPosition(manifest,loser,p,homes[loser]));
      const geometry=spacing.contacts[winner];
      const impactPoint=geometry && geometry.hit.center;
      frame.impacts=hits.filter(hit=>t>=hit.at).map(hit=>{
        // A follow-up has its own sword pose/contact height. Reusing the first
        // contact for both swings detaches the second burst from the blade.
        const sphere=fighter.move.sequence && hit!==hits[0]
          ? fighter.combatGeometry?.hitFrames.find(f=>f.frame===hit.frame)?.spheres.find(s=>s.id===hit.hitbox.ID)
          : null;
        const point=sphere?sphere.center.map(v=>v*(fighter.modelScale ?? 1)):impactPoint;
        return {winner,element:hit.hitbox.Element,damage:hit.hitbox.Damage,age:t-hit.at,
          x:point?homes[winner]+approach(hit.at)+sign*point[0]*FIGHTER_UNIT_SCALE:homes[loser]-sign*35,
          y:point?FLOOR-point[1]*FIGHTER_UNIT_SCALE*CAMERA_VERTICAL_SCALE:FLOOR-125,sign};
      });
      frame.impact=frame.impacts.at(-1);
      if (sinceHit < .12) {
        const soundId=manifest.common.hitSoundIds?.[contact.hitbox['Hit SFX Kind']*3+contact.hitbox['Hit SFX Severity']];
        frame.sounds.push({ id: `contact-${contact.at}`, name: manifest.audio?.[`sound-${soundId}`] ? `sound-${soundId}` : `${fighters[winner].replace(/-left$/, '')}-hit` });
      }
      if (t >= koAt) {
        lose.alpha = 0;
        frame.stocks=[...(state.stocks || [2,2])];
        frame.stocks[loser]=Math.max(0,frame.stocks[loser]-1);
        frame.stockLoss={side:loser,age:t-koAt,index:frame.stocks[loser]};
        frame.ko = { kind: `ko-p${loser+1}`, age: t-koAt, x: sign > 0 ? 1235 : -35, y: 190, sign };
        if (t-koAt < .12) frame.sounds.push({ id: 'ko', name: sign > 0 ? 'ko-right' : 'ko-left' });
      }
      if (damageOverlay) {
        const victim=manifest.fighters[fighters[loser]];
        for (const [index,event] of (damageOverlay.effects || []).entries()) {
          const age=sinceHit-event.frame/60;
          const kind=({1042:'hand-electric',1043:'body-fire',1044:'body-dark'})[event.gfx];
          const effect=kind && manifest.environment[kind];
          const emittedAt=contact.at+event.frame/60;
          if (!effect || event.bone!==141 || age<0 || age>=effect.frames/effect.fps || emittedAt>=koAt) continue;
          // Fire's one-tick emitters leave their particles at the emission
          // point. Moving old flame clouds with the victim erases the trail.
          const snapshot=kind==='body-fire';
          const sampleTime=snapshot?emittedAt:t;
          const sampleFlight=sampleTime<hitAt && !companionHits.length
            ? 1/victim.clips.recoil.fps+Math.max(0,sampleTime-contact.at-contact.hitlag)
            : Math.max(0,sampleTime-hitAt-hitlag);
          const sampleClip=victim.clips[sampleTime<hitAt?'recoil':'hit'];
          const anchors=sampleClip.damageAnchors?.[Math.min(Math.floor(sampleFlight*sampleClip.fps),sampleClip.frames-1)];
          if (!anchors) continue;
          const anchor=anchors[index%5],origin=victim.anchor || [256,330],scale=1.62*fighterScale(victim);
          const position=snapshot?launchPosition(manifest,loser,clamp(sampleFlight/LAUNCH_TIME),homes[loser]):lose;
          const offset=damageModelOffset(manifest,sampleTime-contact.at,contact.hitlag,electric,-sign);
          // Body-attached arcs must remain visible on the damaged silhouette;
          // the separate large contact burst stays behind both fighters.
          frame.effects.push({kind,age,emissionFrame:event.frame,afterFighter:loser,
            x:position.x+offset[0]+(anchor[0]-origin[0])*scale,
            y:position.y+offset[1]+(anchor[1]-origin[1])*scale,scale:PARTICLE_SCALE});
        }
      }
    }
    if(state.celebrate)applyTaunt(frame,state,t,manifest,timing);
    return frame;
  }
  const entrants = state.mode === 'entrance' ? [0, 1] : [1-state.winner];
  const hold = reduced ? 0 : (state.platformHoldSeconds ?? ENTRANCE_HOLD), fall = reduced ? 0 : FALL_TIME;
  for (const side of entrants) {
    const p = positions[side], landingAt = hold+fall;
    // Two stocks identifies fresh/manual entrances in older saved sessions.
    // Result transitions explicitly distinguish a new character from a revival.
    const arrival=state.arrivals?.[side] ?? (state.stocks?.[side] ?? (state.mode==='entrance'?2:1))===2;
    const land = reduced ? 0 : manifest.fighters[fighters[side]].clips.landing.duration;
    if (!reduced && !arrival) {
      if (t < hold) p.overlay = overlayAt(manifest.common.platformOverlay, t);
      else if ((t-hold)*60 < manifest.common.postDropFrames*POST_DROP_DURATION_SCALE) p.overlay = overlayAt(manifest.common.postDropOverlay, t-hold);
    }
    if (t < hold) {
      p.y = SPAWN_Y; frame.platforms.push({ x: p.x, y: SPAWN_Y+4, time: t,
        kind:arrival?'arrival':'revival',scale:arrival?(manifest.fighters[fighters[side]].arrivalPlatformScale ?? 1):1 });
      if(arrival){
        const glow=manifest.environment['arrival-glow'];
        const color=manifest.common.arrival?.overlay;
        if(color)p.overlay=overlayAt(color,t);
        if(glow && t<glow.frames/glow.fps)frame.effects.push({kind:'arrival-glow',age:t,x:p.x,y:p.y,
          scale:FIGHTER_UNIT_SCALE/glow.pixelsPerGameUnit,afterFighter:side});
      }
    } else if (t < landingAt) {
      const progress = clamp((t-hold)/fall);
      p.y = SPAWN_Y+(FLOOR-SPAWN_Y)*progress*progress; p.clip = 'fall'; p.time = t-hold;
      frame.status = 'DROPPING IN';
    } else if (t < landingAt+land) {
      p.clip = 'landing'; p.time = t-landingAt; p.loop = false; frame.status = 'READY';
    } else {
      if (state.mode === 'entrance' || side !== state.winner) p.time = t-landingAt-land;
      frame.status = 'READY';
    }
    const dust = manifest.environment['landing-dust'];
    if (!reduced && t >= landingAt && t < landingAt+dust.frames/dust.fps) {
      frame.effects.push({ kind: 'landing-dust', age: t-landingAt, x: p.x, y: FLOOR, scale: 1.5 });
      frame.sounds.push({ id: `land-${side}`, name: `${fighters[side].replace(/-left$/, '')}-land` });
    }
  }
  if(state.mode==='respawn' && state.tauntStarted!==undefined && !reduced)
    applyTaunt(frame,state,(now-state.tauntStarted)/1000,manifest,{tauntAt:0});
  frame.ready = entrants.every(side => t >= hold+fall+(reduced ? 0 : manifest.fighters[fighters[side]].clips.landing.duration));
  return frame;
}
