import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { advanceAnimationClock, resetAnimationClock, animationFrameIndex } from './animationClock.js';
import { previewFrame, resultTiming } from './animationTimeline.js';

const manifest = JSON.parse(readFileSync(new URL('../public/melee-preview/manifest.json', import.meta.url)));

test('normal refresh rates keep the original animation speed', () => {
  for (const hz of [30, 60, 120]) {
    let clock = resetAnimationClock(1000);
    for (let i=1; i<=hz; i++) clock = advanceAnimationClock(clock, 1000+i*1000/hz);
    assert.ok(Math.abs(clock.time-2000) < .00001);
  }
});

test('a phone hitch before contact cannot skip the bright electric onset', () => {
  const hitMs = resultTiming(manifest, 0).hitAt*1000;
  let clock = resetAnimationClock(hitMs-1000/60);
  clock = advanceAnimationClock(clock, hitMs+150);
  const frame = previewFrame({ mode: 'result', winner: 0, started: 0 }, clock.time, manifest);
  assert.ok(frame.impact.age >= 0 && frame.impact.age < 3/60);
  assert.equal(frame.positions[1].time, 0, 'victim remains in hitstop');
  const next = advanceAnimationClock(clock, clock.real+1000/60);
  assert.ok(Math.abs(next.time-clock.time-1000/60) < .00001, 'resume at normal speed without catch-up');
});

test('returning from a suspended tab does not jump over the whole sequence', () => {
  const clock = advanceAnimationClock(resetAnimationClock(1000), 61000);
  assert.ok(clock.time < 1034);
  assert.deepEqual(resetAnimationClock(62000), { real: 62000, time: 62000 });
});

test('frame stepping after contact visits every particle frame exactly once',()=>{
  for(let contact=1;contact<100;contact++) {
    const frames=Array.from({length:24},(_,offset)=>animationFrameIndex((contact+offset)/60-contact/60,60));
    assert.deepEqual(frames,Array.from({length:24},(_,i)=>i));
  }
});
