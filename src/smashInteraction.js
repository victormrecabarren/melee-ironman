// Charge pauses a move's original action clock, not its hitstop/result clock.
export function chargeProgress(state, now, manifest) {
  const config=manifest.fighters[state.fighters[state.winner]].move.charge;
  const elapsed=Math.max(0,(now-state.started)/1000);
  const holdAt=config.frame/60, maximum=config.frames/60;
  const held=Math.min(maximum,Math.max(0,elapsed-holdAt));
  return {sourceTime:Math.min(elapsed,holdAt),held,frames:Math.min(config.frames,Math.floor(held*60+1e-7)),
    charging:elapsed>=holdAt,complete:elapsed>=holdAt+maximum};
}

export function chargedHitbox(hitbox, charge, frames) {
  if(!charge || !frames)return hitbox;
  const factor=1+(charge.damageMultiplier-1)*Math.min(charge.frames,frames)/charge.frames;
  return {...hitbox,Damage:hitbox.Damage*factor};
}
