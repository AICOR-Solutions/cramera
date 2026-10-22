import assert from 'node:assert/strict';
import { test } from 'node:test';

import * as THREE from 'three';

import { PULL_INTERVAL, PullGesture, objectKeyOf, pullTarget } from '../../src/cramera_laboratory/web/pull-gesture.js';
import { FakeCanvas } from './fakes.mjs';

const KEY = 'tube_clear';
const CENTRE = { clientX: 100, clientY: 100 };

function setUp() {
  const canvas = new FakeCanvas();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 100);
  camera.position.set(0, 0, 2);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld();
  const objects = new THREE.Group();
  const holder = new THREE.Group();
  holder.userData.objectKey = KEY;
  holder.position.set(0, 0, 0.1);
  holder.add(new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.2, 0.2)));
  objects.add(holder);
  objects.updateMatrixWorld(true);
  const controls = { enabled: true };
  const pulls = [];
  const releases = [];
  let time = 0;
  const gesture = new PullGesture(canvas, camera, controls, (key, target) => pulls.push({ key, target }), () => releases.push(true), () => time);
  return { canvas, gesture, objects, controls, pulls, releases, advance: (milliseconds) => { time += milliseconds; } };
}

test('a pull target moves the origin as far as the pointer moved', () => {
  assert.deepEqual(pullTarget([1, 2, 3], new THREE.Vector3(0, 0, 0), new THREE.Vector3(0.5, -0.5, 0)), [1.5, 1.5, 3]);
});

test('a part of a scene object names the object', () => {
  const holder = new THREE.Group();
  holder.userData.objectKey = KEY;
  const part = new THREE.Mesh();
  holder.add(part);
  assert.equal(objectKeyOf(part), KEY);
  assert.equal(objectKeyOf(new THREE.Mesh()), null);
});

test('shift dragging a pullable object pulls it and letting go releases it', () => {
  const { canvas, gesture, objects, controls, pulls, releases, advance } = setUp();
  gesture.attach(objects, [KEY]);
  canvas.dispatch('pointerdown', { ...CENTRE, shiftKey: true, button: 0 });
  assert.equal(gesture.drag.key, KEY);
  assert.equal(controls.enabled, false);
  advance(PULL_INTERVAL);
  canvas.dispatch('pointermove', { clientX: 120, clientY: 100 });
  canvas.dispatch('pointermove', { clientX: 140, clientY: 100 });
  assert.equal(pulls.length, 1);
  assert.equal(pulls[0].key, KEY);
  assert.ok(pulls[0].target[0] > 0);
  assert.ok(Math.abs(pulls[0].target[2] - 0.1) < 1e-9);
  canvas.dispatch('pointerup', {});
  assert.deepEqual(releases, [true]);
  assert.equal(controls.enabled, true);
});

test('without shift or for another object nothing is pulled', () => {
  const { canvas, gesture, objects, pulls } = setUp();
  gesture.attach(objects, [KEY]);
  canvas.dispatch('pointerdown', { ...CENTRE, shiftKey: false, button: 0 });
  assert.equal(gesture.drag, null);
  gesture.attach(objects, ['stopper']);
  canvas.dispatch('pointerdown', { ...CENTRE, shiftKey: true, button: 0 });
  assert.equal(gesture.drag, null);
  assert.deepEqual(pulls, []);
});

test('a detached gesture ignores the pointer and disposing removes it', () => {
  const { canvas, gesture, objects } = setUp();
  gesture.attach(objects, [KEY]);
  gesture.detach();
  canvas.dispatch('pointerdown', { ...CENTRE, shiftKey: true, button: 0 });
  assert.equal(gesture.drag, null);
  gesture.dispose();
  assert.equal(canvas.listeners.get('pointerdown').size, 0);
});
