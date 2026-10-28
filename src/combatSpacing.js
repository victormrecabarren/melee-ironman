import { scaledCombatGeometry } from './fighterScale.js';
// Posed disc geometry, expressed in game units. Layout/approach are preview
// choreography; this does not simulate the full Melee collision engine.
export const WORLD_CENTER=600;
export const GAME_UNIT=512/4.8*.1*1.62;
export const DEFAULT_HOME=[410,790];
const cache=new WeakMap();

export function capsuleContact(hit, capsule) {
  const h=hit.center,a=capsule.a,d=capsule.b.map((v,i)=>v-a[i]);
  const radius=hit.radius+capsule.radius;
  const dy=h[1]-a[1],dz=h[2]-a[2],q=d[1]**2+d[2]**2;
  let lo=0,hi=1;
  if(q>1e-12) {
    const b=-2*(dy*d[1]+dz*d[2]),c=dy*dy+dz*dz-radius*radius,disc=b*b-4*q*c;
    if(disc<0)return null;
    lo=Math.max(0,(-b-Math.sqrt(disc))/(2*q));hi=Math.min(1,(-b+Math.sqrt(disc))/(2*q));
    if(lo>hi)return null;
  } else if(dy*dy+dz*dz>radius*radius)return null;
  const value=t=>h[0]+a[0]+d[0]*t+Math.sqrt(Math.max(0,radius*radius-(dy-d[1]*t)**2-(dz-d[2]*t)**2));
  // Concave support function of a capsule; includes endpoint contacts.
  const ends=[lo,hi];
  for(let i=0;i<32;i++) {const u=(2*lo+hi)/3,v=(lo+2*hi)/3;if(value(u)<value(v))lo=u;else hi=v;}
  const t=[...ends,(lo+hi)/2].reduce((best,t)=>value(t)>value(best)?t:best,ends[0]);
  return {distance:value(t),hit,body:a.map((v,i)=>v+d[i]*t)};
}

export function matchupSpacing(manifest,keys=['dr-mario','roy-left']) {
  if(!manifest)return {homes:DEFAULT_HOME,contacts:[null,null]};
  let entries=cache.get(manifest);if(!entries){entries=new Map();cache.set(manifest,entries);}
  const id=keys.join('|');if(entries.has(id))return entries.get(id);
  const fighters=keys.map(k=>manifest.fighters[k]);
  const contacts=fighters.map((f,side)=>{
    const phase=f && (f.move.hitPhases?.[0] || {frame:f.move.activeStart,hitbox:f.move.hitboxes.find(h=>h.ID===f.move.selectedHitbox)}),geometry=scaledCombatGeometry(f),victim=scaledCombatGeometry(fighters[1-side]);
    if(!geometry || !victim || !phase)return null;
    const end=f.move.hitPhases?.[1]?.frame ?? f.move.activeEnd;
    const frames=geometry.hitFrames.filter(x=>x.frame>=phase.frame && x.frame<end);
    // Preserve the selected damage/element (e.g. Roy's strong hilt, not weak tip).
    const options=frames.flatMap(frame=>frame.spheres
      .filter(h=>h.damage===phase.hitbox.Damage && h.element===phase.hitbox.Element)
      .flatMap(hit=>victim.hurtCapsules.map(c=>{const contact=capsuleContact(hit,c);return contact && {...contact,frame:frame.frame};}))).filter(Boolean);
    if(!options.length)return null;
    const peak=Math.max(...options.map(c=>c.distance));
    const first=Math.min(...options.filter(c=>c.distance>=peak-.1).map(c=>c.frame));
    const best=options.filter(c=>c.frame===first).reduce((a,b)=>a.distance>b.distance?a:b);
    return {...best,distance:Math.max(1,best.distance-.35)}; // small visible overlap at contact
  });
  const gap=Math.max(22,...contacts.map(c=>c?c.distance+2:0))*GAME_UNIT;
  const result={homes:[WORLD_CENTER-gap/2,WORLD_CENTER+gap/2],contacts};entries.set(id,result);return result;
}
export function matchupHomes(manifest,keys) {return matchupSpacing(manifest,keys).homes;}
