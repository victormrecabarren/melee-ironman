import { fighterScale } from './fighterScale.js';
import { companionPosition } from './previewCompanions.js';
import { matchupHomes } from './combatSpacing.js';
// Orthographic adaptation of Melee's fighter tracking to sprite atlases.
// Stage limits are extracted from GrNLa.dat; framing/easing are presentation
// choices for this viewport, not an emulation of the game's 3D camera solver.
export const VIEW = { width: 1200, height: 620 };
export const WORLD_CENTER = 600;
export const WORLD_FLOOR = 456;
export const FIGHTER_SCALE = 1.62;
export const GAME_UNIT = 512/4.8*.1*FIGHTER_SCALE;
const clamp = (x, a=0, b=1) => Math.max(a, Math.min(b, x));
const smooth = x => { x=clamp(x); return x*x*(3-2*x); };
const mix = (a,b,p) => a+(b-a)*p;
export const MOBILE_VIEW = { width:600, height:900 };
export function readyCamera(view,manifest,keys) {
  const base={x:600,y:view.width<800?225:210,zoom:view.width<800?.9:.7};
  if(!manifest || !keys)return base;
  const homes=matchupHomes(manifest,keys);
  let left=Infinity,right=-Infinity,top=Infinity,bottom=-Infinity;
  keys.forEach((key,side)=>{
    const primary={fighter:key,x:homes[side]};
    for(const position of [primary,companionPosition(primary,side,manifest)].filter(Boolean)) {
      const fighter=manifest.fighters[position.fighter],b=fighter?.readyBounds;
      if(!b)continue;
      const scale=FIGHTER_SCALE*fighterScale(fighter),anchor=fighter.anchor || [256,330],home=position.x;
      left=Math.min(left,home+(b[0]-anchor[0])*scale);right=Math.max(right,home+(b[2]-anchor[0])*scale);
      top=Math.min(top,150+(b[1]-anchor[1])*scale);bottom=Math.max(bottom,WORLD_FLOOR+(b[3]-anchor[1])*scale);
    }
  });
  if(!Number.isFinite(left))return base;
  const zoom=Math.min(base.zoom,(view.width-100)/(2*Math.max(600-left,right-600)),(view.height-170)/(bottom-top));
  return {x:600,y:Math.min(Math.max(base.y,bottom-(view.height/2-80)/zoom),top+(view.height/2-90)/zoom),zoom};
}
const blend = (a,b,p) => ({ x:mix(a.x,b.x,p), y:mix(a.y,b.y,p), zoom:mix(a.zoom,b.zoom,p) });

export function project(camera, x, y, view=VIEW) {
  return { x:view.width/2+(x-camera.x)*camera.zoom, y:view.height/2+(y-camera.y)*camera.zoom };
}

export function stageScale(manifest) {
  const p=manifest.stageInfo.projection;
  return GAME_UNIT/(manifest.environment.stage.width/p.stageOrthoWidth*p.gameUnitMeters);
}

export function launchPosition(manifest, side, progress, home, floor=WORLD_FLOOR) {
  const sign=side===1?1:-1;
  const edge=manifest.stageInfo.blastBounds[sign>0?'right':'left'];
  const end=WORLD_CENTER+edge*GAME_UNIT;
  const distance=Math.abs(end-home);
  // Strong initial launch, then deceleration; shared by camera and timeline.
  const p=(1-Math.exp(-2.3*clamp(progress)))/(1-Math.exp(-2.3));
  return { x:home+sign*distance*p, y:floor-distance*(.2*p-.032*p*p) };
}

function trackCamera(manifest, winner, victim, view) {
  const b=manifest.stageInfo.cameraBounds;
  const left=600+b.left*GAME_UNIT, right=600+b.right*GAME_UNIT;
  const top=WORLD_FLOOR-b.top*GAME_UNIT, bottom=WORLD_FLOOR-b.bottom*GAME_UNIT;
  const x=clamp(victim.x,left,right), y=clamp(victim.y,top,bottom);
  const zoom=clamp(Math.min((view.width-120)/(Math.abs(x-winner.x)+500), (view.height-140)/(Math.abs(y-winner.y)+450)), view.width < 800 ? .48 : .24, readyCamera(view).zoom);
  return { zoom,
    x:clamp(clamp((winner.x+x)/2, winner.x-(view.width/2-100)/zoom, winner.x+(view.width/2-100)/zoom), left+view.width/2/zoom, right-view.width/2/zoom),
    y:clamp((winner.y+y)/2-160, top+view.height/2/zoom, bottom-view.height/2/zoom) };
}

export function composeView(frame, state, t, manifest, timing, reduced, view=VIEW) {
  const READY=readyCamera(view,manifest,state.fighters || ['dr-mario','roy-left']);
  const RESET=state.nextFighters?readyCamera(view,manifest,state.nextFighters):READY;
  let camera=READY;
  if (!reduced && state.mode==='result') {
    const flight=Math.max(0,t-timing.hitAt-timing.hitlag);
    const winner=frame.cameraWinner || frame.positions[state.winner], loser=1-state.winner;
    const target=trackCamera(manifest,winner,frame.positions[loser],view);
    camera=blend(READY,target,smooth(flight/.24));
    if (t>=timing.koAt) camera=blend(camera,RESET,smooth((t-timing.koAt-.15)/.65));
  }
  frame.camera=camera;
  if (frame.impact && !reduced) {
    const loser=1-frame.impact.winner, p=frame.positions[loser];
    const point=project(camera,p.x,p.y-140,view);
    if (!frame.ko && (point.x < -40 || point.x > view.width+40 || point.y < -40)) {
      p.alpha=0;
      frame.magnifier={ side:loser, sign:loser===1?1:-1, clip:p.clip,time:p.time,loop:p.loop,overlay:p.overlay,fighter:p.fighter,
        x:clamp(point.x,72,view.width-72),y:clamp(point.y,85,view.height-130) };
    }
    if (frame.ko) {
      // This is an edge overlay, not a world object. World-unit conversion
      // magnified it ~10x on portrait screens. Keep a stable viewport-relative
      // footprint through the camera return, using the source frames unchanged.
      frame.ko.scale=Math.min(view.width,view.height)*2.76/620;
      const quake=manifest.common.koQuake;
      const offset=quake?.offsets[Math.floor((frame.ko.age+1e-9)*quake.fps)];
      // Camera_ApplyQuake uses a 10x channel multiplier. Adapt its viewport
      // amplitude here; retain the source's irregular 22-frame waveform.
      frame.shake=offset?[offset[0]*10*view.height/620,-offset[1]*10*view.height/620]:[0,0];
      frame.ko.x=loser===1?view.width+35:-35;
      frame.ko.y=clamp(point.y,100,view.height-170);
    }
  }
  return frame;
}

// Semantic buttons cover the settled fighters, in the same projection as canvas.
export function fighterTarget(view, home, manifest, keys) {
  const camera=readyCamera(view,manifest,keys);
  const side=matchupHomes(manifest,keys).indexOf(home);
  const partner=side>=0?companionPosition({fighter:keys[side],x:home},side,manifest):null;
  const left=Math.min(home,partner?.x ?? home)-110;
  const width=220+Math.abs((partner?.x ?? home)-home);
  const point=project(camera,left,WORLD_FLOOR-330,view);
  return { left:point.x/view.width*100, top:point.y/view.height*100,
    width:width*camera.zoom/view.width*100, height:350*camera.zoom/view.height*100 };
}
