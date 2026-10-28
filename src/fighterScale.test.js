import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fighterScale,scaledCombatGeometry} from './fighterScale.js';
const manifest=JSON.parse(readFileSync(new URL('../public/melee-preview/manifest.json',import.meta.url)));

test('all roster facings have source runtime scales, distinct from export framing',()=>{
  assert.equal(Object.keys(manifest.fighters).length,54);
  for(const [key,f] of Object.entries(manifest.fighters)){
    assert.equal(f.modelScaleVersion,'disc-model-scale-v1',key);
    assert.ok(f.modelScale>=.1 && f.modelScale<=4,key);
    const other=manifest.fighters[key.endsWith('-left')?key.slice(0,-5):key+'-left'];
    assert.equal(f.modelScale,other.modelScale,key);
  }
  for(const [key,expected] of Object.entries({pichu:.5,pikachu:.9,bowser:.69,mario:1.1,sheik:1.4,roy:1.08})){
    assert.ok(Math.abs(manifest.fighters[key].modelScale-expected)<1e-6,key);
  }
});

test('sizing keeps export projection, gameplay size, and hit radii separate',()=>{
 const geometry={hurtCapsules:[{a:[2,4,0],b:[2,8,0],radius:3}],hitFrames:[{frame:1,spheres:[{center:[10,6,2],radius:4}]}]};
 const fighter={scale:2,modelScale:.5,combatGeometry:geometry};
 assert.equal(fighterScale(fighter),1);
 const g=scaledCombatGeometry(fighter);
 assert.deepEqual(g.hurtCapsules[0],{a:[1,2,0],b:[1,4,0],radius:1.5});
 assert.deepEqual(g.hitFrames[0].spheres[0],{center:[5,3,1],radius:4});
 assert.equal(geometry.hurtCapsules[0].radius,3,'source geometry must not accumulate scaling on repeated matchups');
 assert.deepEqual(scaledCombatGeometry(fighter),g);
});
