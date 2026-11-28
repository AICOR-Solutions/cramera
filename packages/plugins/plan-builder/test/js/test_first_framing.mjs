import { test } from 'node:test';
import assert from 'node:assert/strict';

import { FirstFraming, WorkAreaFraming } from '../../src/cramera_plan_builder/web/builder/plan-scene.js';
import { Bounds } from 'cramera-viewer/scene/bounds.js';

// %% framing the robot once its model is loaded

test('the view frames the scene again once the first robot model is loaded', () => {
  const framing = new FirstFraming();
  assert.equal(framing.frameOnModelLoaded(), true);
  assert.equal(framing.frameOnModelLoaded(), false);
});

test('a camera the person moved is not framed again when a robot model is loaded', () => {
  const framing = new FirstFraming();
  framing.notePersonMoved();
  assert.equal(framing.frameOnModelLoaded(), false);
});

// %% framing the robot's work area in a large environment

test('the view frames a room-sized environment whole', () => {
  const room = new Bounds([-1, -2, 0], [3, 2, 2.5]);
  const markers = new Bounds([0, -0.3, 0], [0.6, 0.3, 1.8]);
  assert.deepEqual(WorkAreaFraming.bounds(room, markers), room);
});

test('in an environment larger than a room the view frames the robot and its table', () => {
  const lab = new Bounds([-40, -10, 0], [30, 12, 6]);
  const markers = new Bounds([0, -0.3, 0], [0.6, 0.3, 1.8]);
  const framed = WorkAreaFraming.bounds(lab, markers);
  const margin = WorkAreaFraming.MARGIN;
  assert.deepEqual(framed.min, [-margin, -0.3 - margin, 0]);
  assert.deepEqual(framed.max, [0.6 + margin, 0.3 + margin, 1.8]);
});

test('without markers the view frames the environment, and without either the floor', () => {
  const lab = new Bounds([-40, -10, 0], [30, 12, 6]);
  assert.deepEqual(WorkAreaFraming.bounds(lab, null), lab);
  const markers = new Bounds([0, 0, 0], [1, 1, 1]);
  assert.deepEqual(WorkAreaFraming.bounds(null, markers), markers);
  assert.equal(WorkAreaFraming.bounds(null, null), null);
});
