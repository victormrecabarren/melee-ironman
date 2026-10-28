import {CHARACTER_ROSTER, initialLineup, lineupFighters} from './previewRoster.js';
import {ENTRANCE_HOLD} from './animationTimeline.js';

export const PREVIEW_SESSION_KEY='melee-ironman:animation-session:v1';
const slugs=new Set(CHARACTER_ROSTER.map(c=>c.slug));
const pair=value=>Array.isArray(value) && value.length===2;
const stocks=value=>pair(value) && value.every(n=>Number.isInteger(n) && n>=0 && n<=2);
const fighters=value=>pair(value) && value.every(s=>typeof s==='string' && slugs.has(s.replace(/-left$/,'')));
function validLineup(value) {
  return value && pair(value.players) && [null,0,1].includes(value.champion) &&
    value.players.every(p=>p && Number.isInteger(p.index) && p.index>=0 && p.index<=CHARACTER_ROSTER.length &&
      Number.isInteger(p.stocks) && p.stocks>=0 && p.stocks<=2 &&
      (p.index===CHARACTER_ROSTER.length ? p.stocks===0 && value.champion!==null : p.stocks>0)) &&
    pair(value.played) && value.played.every(list=>Array.isArray(list) && list.every(s=>slugs.has(s))) &&
    Array.isArray(value.stockHistory) && value.stockHistory.every(e=>e && [0,1].includes(e.side) && slugs.has(e.character) && slugs.has(e.victim));
}
export function parsePreviewSession(raw) {
  const s=JSON.parse(raw),p=s?.playback;
  if(s?.version!==1 || !validLineup(s.lineup) || (s.pending!==null && !validLineup(s.pending)) ||
    !Array.isArray(s.history) || !s.history.every(validLineup) ||
    !p || !['entrance','respawn','result'].includes(p.mode) || !fighters(p.fighters) || !stocks(p.stocks) ||
    (p.mode!=='entrance' && ![0,1].includes(p.winner)) ||
    (p.nextFighters!==undefined && !fighters(p.nextFighters)) ||
    (p.nextStocks!==undefined && !stocks(p.nextStocks)) ||
    (p.chargeFrames!==undefined && (!Number.isInteger(p.chargeFrames) || p.chargeFrames<0 || p.chargeFrames>60)) ||
    (p.celebrate!==undefined && typeof p.celebrate!=='boolean') ||
    (p.tauntStarted!==undefined && (p.mode!=='respawn' || !Number.isFinite(p.tauntStarted))) ||
    (p.platformHoldSeconds!==undefined && (!['entrance','respawn'].includes(p.mode) || !Number.isFinite(p.platformHoldSeconds) || p.platformHoldSeconds<0 || p.platformHoldSeconds>ENTRANCE_HOLD)) ||
    (p.arrivals!==undefined && (!pair(p.arrivals) || !p.arrivals.every(value=>typeof value==='boolean'))) ||
    (p.matchStart!==undefined && typeof p.matchStart!=='boolean') ||
    (p.awaitingStart!==undefined && (typeof p.awaitingStart!=='boolean' || (p.awaitingStart && (p.mode!=='entrance' || !p.matchStart)))) ||
    p.started!==0 || (p.idleSince!==undefined && (!pair(p.idleSince) || !p.idleSince.every(Number.isFinite))) ||
    !Number.isFinite(s.elapsed) || s.elapsed<0 || !Array.isArray(s.playedSounds) || !s.playedSounds.every(x=>typeof x==='string') ||
    typeof s.sound!=='boolean' || typeof s.reduced!=='boolean')throw new Error('Invalid saved match');
  return s;
}
export function readPreviewSession(storage) {
  try {
    const raw=(storage || globalThis.localStorage).getItem(PREVIEW_SESSION_KEY);
    return {session:raw?parsePreviewSession(raw):null,error:''};
  } catch {
    return {session:null,error:'The saved match could not be restored. Changes will be saved when browser storage is available.'};
  }
}
export function capturePreviewSession({lineup,pending,history,playback,now,playedSounds,sound,reduced}) {
  // A held pointer is transient input, never a committed stock. Returning to
  // the tab must not resume an abandoned hold or auto-award a win.
  if(playback.mode==='charge') {
    playback={mode:'entrance',started:now-3000,fighters:playback.fighters,stocks:playback.stocks};
    playedSounds=[];
  }
  return {version:1,lineup,pending,history,elapsed:Math.max(0,now-playback.started),sound,reduced,
    playedSounds:[...playedSounds],playback:{...playback,started:0,
      ...(playback.tauntStarted!==undefined?{tauntStarted:playback.tauntStarted-playback.started}:{}),
      ...(playback.idleSince?{idleSince:playback.idleSince.map(t=>t-playback.started)}:{})}};
}
export function restorePreviewPlayback(session,now) {
  const started=now-session.elapsed;
  return {...session.playback,started,
    ...(session.playback.tauntStarted!==undefined?{tauntStarted:started+session.playback.tauntStarted}:{}),
    ...(session.playback.idleSince?{idleSince:session.playback.idleSince.map(t=>started+t)}:{})};
}
export function writePreviewSession(session,storage) {
  try {
    (storage || globalThis.localStorage).setItem(PREVIEW_SESSION_KEY,JSON.stringify(session));
    return '';
  } catch {
    return 'This browser could not save the match. Keep this tab open until browser storage is available.';
  }
}

export function freshPreviewSession(reduced=false) {
  const lineup=initialLineup();
  return capturePreviewSession({lineup,pending:null,history:[],
    playback:{mode:'entrance',started:0,fighters:lineupFighters(lineup),stocks:[2,2],matchStart:true,awaitingStart:true},
    now:0,playedSounds:[],sound:true,reduced});
}
