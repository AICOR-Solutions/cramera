import { test } from 'node:test';
import assert from 'node:assert/strict';

import { aboutAxis, multiply, rotated, separation, shifted, zAxis } from '../pose-math.js';

const IDENTITY = [0, 0, 0, 1];
const QUARTER_TURN = Math.PI / 2;

test('turning about an axis twice by a quarter is a half turn', () => {
  const half = multiply(aboutAxis(0, QUARTER_TURN), aboutAxis(0, QUARTER_TURN));
  aboutAxis(0, Math.PI).forEach((value, index) => assert.ok(Math.abs(value - half[index]) < 1e-12));
});

test('the identity leaves the z axis and a quarter turn about x tips it over', () => {
  assert.deepEqual(zAxis(IDENTITY), [0, 0, 1]);
  const tipped = zAxis(aboutAxis(0, QUARTER_TURN));
  [0, -1, 0].forEach((value, index) => assert.ok(Math.abs(value - tipped[index]) < 1e-12));
});

test('a pose turned in place keeps its position', () => {
  const pose = [1, 2, 3, ...IDENTITY];
  const turned = rotated(pose, 2, QUARTER_TURN);
  assert.deepEqual(turned.slice(0, 3), pose.slice(0, 3));
  assert.deepEqual(turned.slice(3), aboutAxis(2, QUARTER_TURN));
});

test('a shifted pose keeps its orientation and rounds its position', () => {
  assert.deepEqual(shifted([0.1, 0.2, 0.3, ...IDENTITY], [0.2, 0, 0], 6), [0.3, 0.2, 0.3, ...IDENTITY]);
});

test('the separation of two poses is their distance and angle', () => {
  const { distance, angle } = separation([0, 0, 0, ...IDENTITY], [3, 4, 0, ...aboutAxis(2, QUARTER_TURN)]);
  assert.equal(distance, 5);
  assert.ok(Math.abs(angle - QUARTER_TURN) < 1e-12);
});
