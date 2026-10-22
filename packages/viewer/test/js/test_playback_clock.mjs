import { test } from 'node:test';
import assert from 'node:assert/strict';

import { PlaybackClock } from '../../src/cramera/web/playback/playback-clock.js';

test('the frame follows elapsed time and speed, not the number of updates', () => {
  const fewUpdates = new PlaybackClock(10, 101);
  const manyUpdates = new PlaybackClock(10, 101);
  fewUpdates.playing = true;
  manyUpdates.playing = true;
  fewUpdates.advance(1);
  for (let step = 0; step < 100; step++) manyUpdates.advance(0.01);
  assert.equal(fewUpdates.frame, 10);
  assert.equal(manyUpdates.frame, 10);
});

test('speed scales recording time per wall-clock second', () => {
  const clock = new PlaybackClock(20, 200);
  clock.speed = 2.5;
  clock.playing = true;
  clock.advance(1);
  assert.equal(clock.frame, 50);
});

test('a paused clock does not advance', () => {
  const clock = new PlaybackClock(20, 200);
  assert.equal(clock.advance(1), false);
  assert.equal(clock.frame, 0);
});

test('playback stops at the last frame unless it loops', () => {
  const clock = new PlaybackClock(10, 11);
  clock.playing = true;
  clock.advance(5);
  assert.equal(clock.frame, clock.lastFrame);
  assert.equal(clock.playing, false);
  const looping = new PlaybackClock(10, 11);
  looping.looping = true;
  looping.playing = true;
  looping.advance(1.25);
  assert.equal(looping.frame, 2);
  assert.equal(looping.playing, true);
});

test('playing at the end starts over', () => {
  const clock = new PlaybackClock(10, 11);
  clock.seek(clock.lastFrame);
  clock.playing = true;
  assert.equal(clock.frame, 0);
});

test('seeking is clamped to the trajectory and rounds to a frame', () => {
  const clock = new PlaybackClock(10, 11);
  clock.seek(-4);
  assert.equal(clock.frame, 0);
  clock.seek(99);
  assert.equal(clock.frame, 10);
  clock.seek(3.6);
  assert.equal(clock.frame, 4);
  assert.equal(clock.time, 0.4);
});

test('advance reports whether the shown frame changed', () => {
  const clock = new PlaybackClock(10, 100);
  clock.playing = true;
  assert.equal(clock.advance(0.01), false);
  assert.equal(clock.advance(0.1), true);
});

test('a single-frame recording has no duration', () => {
  const clock = new PlaybackClock(30, 1);
  clock.looping = true;
  clock.playing = true;
  clock.advance(1);
  assert.equal(clock.frame, 0);
  assert.equal(clock.duration, 0);
});

test('invalid rates and speeds are refused', () => {
  assert.throws(() => new PlaybackClock(0, 10), RangeError);
  assert.throws(() => { new PlaybackClock(10, 10).speed = 0; }, RangeError);
});
