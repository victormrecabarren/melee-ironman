import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {initialLineup,takeStock,lineupFighters,CHARACTER_ROSTER} from './previewRoster.js';
import {previewFrame,resultTiming} from './animationTimeline.js';
const manifest=JSON.parse(readFileSync(new URL('../public/melee-preview/manifest.json',import.meta.url)));
test('one tap removes one stock; the second advances only the defeated side',()=>{
 const start=initialLineup(),one=takeStock(start,0),two=takeStock(one,0);
 assert.deepEqual(start.players.map(p=>p.stocks),[2,2]);
 assert.deepEqual(one.players,[{index:0,stocks:2},{index:0,stocks:1}]);
 assert.deepEqual(two.players,[{index:0,stocks:2},{index:1,stocks:2}]);
 assert.deepEqual(lineupFighters(two),['dr-mario','marth-left']);
 assert.deepEqual(takeStock(two,1).players,[{index:0,stocks:1},{index:1,stocks:2}]);
});
test('all 26 fighters receive exactly two stocks; final KO ends without wrapping',()=>{
 for(const winner of [0,1]){
  let state=initialLineup();
  for(let stock=0;stock<52;stock++){
   assert.equal(state.champion,null);
   assert.equal(state.players[1-winner].index,Math.floor(stock/2));
   state=takeStock(state,winner);
  }
  assert.equal(state.champion,winner);
  assert.equal(state.players[1-winner].stocks,0);
  assert.equal(state.players[1-winner].index,CHARACTER_ROSTER.length);
  assert.throws(()=>takeStock(state,winner));
 }
});
for(const winner of [0,1])for(const remaining of [2,1])test(`P${winner+1} KO: ${remaining} → ${remaining-1} at blast; reset only on entrance`,()=>{
 const stocks=[2,2];stocks[1-winner]=remaining;
 const state={mode:'result',winner,started:0,stocks,nextStocks:[2,2],fighters:['dr-mario','roy-left'],nextFighters:['dr-mario','roy-left']};
 const timing=resultTiming(manifest,winner);
 assert.deepEqual(previewFrame(state,(timing.koAt-.001)*1000,manifest).stocks,stocks);
 const atBlast=previewFrame(state,(timing.koAt+.001)*1000,manifest);
 assert.equal(atBlast.stocks[1-winner],remaining-1);
 assert.equal(atBlast.stockLoss.index,remaining-1);
 assert.equal(previewFrame(state,(timing.end-.001)*1000,manifest).stocks[1-winner],remaining-1);
 assert.deepEqual(previewFrame(state,(timing.end+.001)*1000,manifest).stocks,[2,2]);
});
test('reduced motion still consumes a stock and final elimination stays at zero',()=>{
 const state={mode:'result',winner:0,started:0,stocks:[2,1],finishedRun:true};
 assert.deepEqual(previewFrame(state,300,manifest,true).stocks,[2,0]);
 const completed=previewFrame(state,20000,manifest,true);
 assert.equal(completed.complete,true);assert.deepEqual(completed.stocks,[2,0]);assert.equal(completed.next,undefined);
});

test('stock art and loss particles retain original disc provenance',()=>{
 for(const character of CHARACTER_ROSTER){
  const icon=manifest.environment['stock-'+character.slug];
  assert.ok(icon.source.startsWith('IfAll.dat: Stc_scemdls'));
  assert.equal(icon.frames,1);assert.equal(icon.lossFrames,10);assert.equal(icon.fps,60);
  assert.deepEqual(icon.lossOffsets[0],[0,0]);
 }
 assert.match(manifest.environment['stock-loss'].source,/generator 247/);
});

test('manual correction data remains independent from earlier undo snapshots',()=>{
 const before=initialLineup(),after=takeStock(before,0);
 const corrected={players:after.players.map(p=>({...p})),champion:null};
 corrected.players[0]={index:1,stocks:1};
 assert.deepEqual(lineupFighters(corrected),['mario','roy-left']);
 assert.deepEqual(before.players,[{index:0,stocks:2},{index:0,stocks:2}]);
 assert.deepEqual(after.players,[{index:0,stocks:2},{index:0,stocks:1}]);
});

test('all 26 roster choices have both actual facings and complete source clips',()=>{
 for(const character of CHARACTER_ROSTER)for(const [suffix,facing] of [['','right'],['-left','left']]){
  const f=manifest.fighters[character.slug+suffix];
  assert.ok(f,character.slug+suffix);assert.equal(f.facing,facing);
  assert.deepEqual(Object.keys(f.clips).sort(),['fall','hit','idle','landing','recoil','smash','taunt','tumble']);
  assert.equal(f.materialVersion,'source-specular-v1');
  assert.equal(f.combatGeometry.version,'posed-hitboxes-v1');
 }
});

test('stats keep victim icons in KO order, including repeat opponents',async()=>{
 const {playerStockStats,withPlayedCharacters}=await import('./previewRoster.js');
 let state=initialLineup();
 const marth=CHARACTER_ROSTER.findIndex(c=>c.slug==='marth');
 state=withPlayedCharacters({...state,players:[state.players[0],{index:CHARACTER_ROSTER.length-1-marth,stocks:2}]});
 state=takeStock(takeStock(state,0),0);
 state=withPlayedCharacters({...state,players:[state.players[0],{index:0,stocks:2}]});
 state=takeStock(state,0);
 const [doc]=playerStockStats(state,0);
 assert.equal(doc.character.slug,'dr-mario');
 assert.deepEqual(doc.victims.map(c=>c.slug),['marth','marth','roy']);
 assert.equal(playerStockStats(state,1).find(r=>r.character.slug==='marth').victims.length,0);
});
test('stats attribute kills to both sides and undo restores exact immutable history',async()=>{
 const {playerStockStats,withPlayedCharacters}=await import('./previewRoster.js');
 const before=initialLineup(),one=takeStock(before,0),two=takeStock(one,1);
 assert.equal(playerStockStats(before,0)[0].victims.length,0);
 assert.deepEqual(playerStockStats(one,0)[0].victims.map(c=>c.slug),['roy']);
 assert.deepEqual(playerStockStats(two,1)[0].victims.map(c=>c.slug),['dr-mario']);
 assert.equal(playerStockStats(one,1)[0].victims.length,0,'restoring prior snapshot undoes the second kill');
 const corrected=withPlayedCharacters({...two,players:[{index:3,stocks:1},two.players[1]]});
 assert.equal(corrected.stockHistory.length,2,'manual selections invent no kills');
 assert.equal(playerStockStats(corrected,0).at(-1).character.slug,'bowser');
 assert.equal(playerStockStats(corrected,0).at(-1).victims.length,0);
 assert.equal(playerStockStats(two,0).length,1,'correction does not mutate undo snapshot');
});
test('final stock remains in stats after roster exhaustion',async()=>{
 const {playerStockStats}=await import('./previewRoster.js');
 let state=initialLineup();
 for(let i=0;i<52;i++)state=takeStock(state,0);
 assert.equal(state.champion,0);
 assert.equal(playerStockStats(state,0)[0].victims.length,52);
 assert.equal(playerStockStats(state,1).length,26);
 assert.equal(playerStockStats(state,0)[0].victims.at(-1).slug,'dr-mario');
});
