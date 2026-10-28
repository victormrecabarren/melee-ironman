// Export-camera compensation and the disc's runtime model scale are distinct.
export const fighterScale = fighter => (fighter?.scale ?? 1)*(fighter?.modelScale ?? 1);

export function scaledCombatGeometry(fighter) {
  const geometry=fighter?.combatGeometry;
  if(!geometry)return null;
  const scale=fighter.modelScale ?? 1;
  const point=p=>p.map(x=>x*scale);
  return {...geometry,
    // Hurt radius follows its joint matrix; hit radius is already in world
    // units (lbColl_80007ECC uses match-size x34_scale.y, not model_scaling).
    hurtCapsules:geometry.hurtCapsules.map(c=>({...c,a:point(c.a),b:point(c.b),radius:c.radius*scale})),
    hitFrames:geometry.hitFrames.map(f=>({...f,spheres:f.spheres.map(h=>({...h,center:point(h.center)}))}))};
}
