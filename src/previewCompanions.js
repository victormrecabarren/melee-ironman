// Nana is a separate fighter export, never a recolored/mirrored Popo sprite.
// The stationary preview keeps the pair together; it does not simulate Nana's
// autonomous recovery AI or independent percent. Source input history is five
// slots apart; the supplied 60 Hz clip shows contacts six frames apart (17/23).
// Use that observed delay for this controlled paired forward-smash presentation.
export const NANA_INPUT_DELAY = 6 / 60;
export const PARTNER_SEPARATION = 5 * 17.28;
export const PARTNER_CONTACT_SEPARATION = 1.5 * 17.28;
export function companionKey(key) {
  return key === 'ice-climbers' ? 'nana' : key === 'ice-climbers-left' ? 'nana-left' : null;
}
export function fighterAssetKeys(keys) {
  return [...new Set(keys.filter(Boolean).flatMap(key => [key, companionKey(key)].filter(Boolean)))];
}
export function companionPosition(position, side, manifest) {
  const key=companionKey(position.fighter);
  // Saved selections render their buttons before the asset fetch resolves.
  if (!key || !manifest?.fighters?.[key]) return null;
  const partner={...position, fighter:key, x:position.x+(side===0?-1:1)*PARTNER_SEPARATION};
  if(position.companionMotion) return {...partner,...position.companionMotion,fighter:key};
  if(position.clip==='smash') {
    partner.time=Math.max(0,position.time-NANA_INPUT_DELAY);
    if(position.time<NANA_INPUT_DELAY) { partner.clip='idle'; partner.loop=true; }
  }
  return partner;
}
