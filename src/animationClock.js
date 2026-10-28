// Keep short impact effects visible when a browser callback arrives late.
// Normal 30/60/120 Hz playback follows real time; a hitch pauses the sequence
// instead of skipping ahead through contact, hitstop, and the first sparks.
const MAX_STEP_MS = 1000 / 30;

export function resetAnimationClock(now) {
  return { real: now, time: now };
}

export function advanceAnimationClock(clock, now) {
  const delta = Math.max(0, now-clock.real);
  return { real: now, time: clock.time+Math.min(delta, MAX_STEP_MS) };
}

// Subtracting two 60 Hz timestamps can land just below an integer frame.
// Keep an exact inspector step from repeating one frame and skipping the next.
export function animationFrameIndex(seconds, fps) {
  return Math.floor(Math.max(0,seconds)*fps+1e-7);
}
