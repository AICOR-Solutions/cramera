import { test } from 'node:test';
import assert from 'node:assert/strict';

import { MarkerDrag, MarkerKind, PressTarget, Selection, pressTarget } from '../../src/cramera_plan_builder/web/builder/plan-scene.js';

const target = new Selection(MarkerKind.TARGET, 'step-1', 'target_location');

// %% what a press grabs

test('a press on a handle drags the handle', () => {
  assert.equal(pressTarget(true, target), PressTarget.HANDLE);
  assert.equal(pressTarget(true, null), PressTarget.HANDLE);
});

test('a press on a marker, picked or not, drags the marker', () => {
  assert.equal(pressTarget(false, target), PressTarget.MARKER);
});

test('a press beside every marker turns the camera', () => {
  assert.equal(pressTarget(false, null), PressTarget.CAMERA);
});

// %% dragging a marker

test('a marker does not move while the pointer stays within a click', () => {
  const drag = new MarkerDrag(target, [1, 2], [1.1, 2.1], { x: 100, y: 100 });
  assert.equal(drag.follow([1.2, 2.1], { x: 103, y: 101 }), null);
  assert.equal(drag.moved, false);
});

test('a dragged marker keeps where it was gripped under the pointer', () => {
  const drag = new MarkerDrag(target, [1, 2], [1.1, 2.1], { x: 100, y: 100 });
  const [x, y] = drag.follow([1.6, 1.6], { x: 140, y: 130 });
  assert.ok(Math.abs(x - 1.5) < 1e-9 && Math.abs(y - 1.5) < 1e-9);
  assert.equal(drag.moved, true);
  assert.equal(drag.selection, target);
});

test('a marker once dragged follows the pointer back near where it was pressed', () => {
  const drag = new MarkerDrag(target, [1, 2], [1, 2], { x: 100, y: 100 });
  drag.follow([2, 2], { x: 150, y: 100 });
  assert.deepEqual(drag.follow([1.01, 2], { x: 101, y: 100 }), [1.01, 2]);
});
