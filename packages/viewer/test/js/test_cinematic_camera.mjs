import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import { SegmentKey } from '../../src/cramera/web/protocol.js';
import { CinematicCamera, CloseUp, Framing, REFERENCE_DURATION, SHORTEST_TIMING, ShotPlan, ShotTiming, SLOW_MOTION, smoothstep } from '../../src/cramera/web/scene/cinematic-camera.js';

const FRAMES_PER_SECOND = 10;

const SEGMENTS = [
  { [SegmentKey.STEP]: 'run', [SegmentKey.START]: 0, [SegmentKey.END]: 100 },
  { [SegmentKey.STEP]: 'move', [SegmentKey.START]: 100, [SegmentKey.END]: 200, [SegmentKey.PICKS]: 'milk', [SegmentKey.ATTACH]: 100, [SegmentKey.DETACH]: 180 },
];

/**
 * The parts of a 3D view the camera drives.
 */
class FakeView {
  constructor() {
    this.camera = new THREE.PerspectiveCamera();
    this.camera.up.set(0, 0, 1);
    this.camera.position.set(5, 0, 2);
    this.controls = { target: new THREE.Vector3() };
    this.renders = 0;
  }

  requestRender() {
    this.renders += 1;
  }
}

// %% plan

test('the ramp eases from 0 to 1 and stays there', () => {
  assert.equal(smoothstep(0, 1, -1), 0);
  assert.equal(smoothstep(0, 1, 0.5), 0.5);
  assert.equal(smoothstep(0, 1, 2), 1);
  assert.equal(smoothstep(1, 1, 1), 1);
});

test('every pick-up and letting go of a named object gets a close-up', () => {
  const plan = ShotPlan.of(SEGMENTS, FRAMES_PER_SECOND);
  assert.deepEqual(plan.closeUps.map((closeUp) => [closeUp.time, closeUp.object]), [[10, 'milk'], [18, 'milk']]);
  assert.deepEqual(ShotPlan.of(SEGMENTS, 0).closeUps, []);
});

test('a close-up moves in before its moment, holds, and moves out after it', () => {
  const closeUp = new CloseUp(10, 'milk');
  assert.equal(closeUp.closeness(10 - ShotTiming.LEAD - 0.1), 0);
  assert.equal(closeUp.closeness(10 - ShotTiming.ARRIVE), 1);
  assert.equal(closeUp.closeness(10 + ShotTiming.HOLD), 1);
  const leaving = closeUp.closeness(10 + ShotTiming.HOLD + ShotTiming.EASE_OUT / 2);
  assert.ok(leaving > 0 && leaving < 1);
  assert.equal(closeUp.closeness(10 + ShotTiming.HOLD + ShotTiming.EASE_OUT + 0.1), 0);
});

test('between close-ups the shot is wide and names no object', () => {
  const plan = ShotPlan.of(SEGMENTS, FRAMES_PER_SECOND);
  assert.deepEqual(plan.shotAt(2), { closeness: 0, object: null });
  assert.deepEqual(plan.shotAt(10), { closeness: 1, object: 'milk' });
});

test('a short recording keeps its close-ups short', () => {
  const short = ShotPlan.of(SEGMENTS, FRAMES_PER_SECOND, REFERENCE_DURATION / 4);
  assert.deepEqual(short.closeUps.map((closeUp) => closeUp.scale), [0.25, 0.25]);
  assert.equal(short.shotAt(10 - ShotTiming.LEAD / 2).closeness, 0);
  assert.equal(ShotPlan.of(SEGMENTS, FRAMES_PER_SECOND, 0.1).closeUps[0].scale, SHORTEST_TIMING);
});

test('the playback slows down while the camera is close', () => {
  const plan = ShotPlan.of(SEGMENTS, FRAMES_PER_SECOND);
  assert.equal(plan.pace(2), 1);
  assert.equal(plan.pace(10), 1 - SLOW_MOTION);
  const camera = new CinematicCamera(new FakeView());
  camera.plan(plan);
  assert.equal(camera.pace(10), 1, 'a camera that is off leaves the speed alone');
  camera.enabled = true;
  assert.equal(camera.pace(10), 1 - SLOW_MOTION);
});

// %% camera

test('a disabled camera leaves the view alone', () => {
  const view = new FakeView();
  const camera = new CinematicCamera(view);
  assert.equal(camera.update(0, new THREE.Vector3(), () => null), false);
  assert.deepEqual(view.camera.position.toArray(), [5, 0, 2]);
});

test('the wide shot looks at the robot from the wide distance, starting where the camera was', () => {
  const view = new FakeView();
  const camera = new CinematicCamera(view);
  camera.enabled = true;
  camera.plan(ShotPlan.of(SEGMENTS, FRAMES_PER_SECOND));
  const robot = new THREE.Vector3(1, 1, 0);
  assert.equal(camera.update(0, robot, () => null), true);
  const look = robot.clone().add(new THREE.Vector3(0, 0, Framing.ROBOT_LOOK_HEIGHT));
  assert.deepEqual(view.controls.target.toArray(), look.toArray());
  assert.ok(Math.abs(view.camera.position.distanceTo(look) - Framing.WIDE_DISTANCE) < 1e-9);
  const azimuth = Math.atan2(view.camera.position.y - robot.y, view.camera.position.x - robot.x);
  assert.ok(Math.abs(azimuth - Math.atan2(-1, 4)) < 1e-9);
  assert.equal(view.renders, 1);
});

test('at a pick-up the camera closes in on the object, easing frame by frame', () => {
  const view = new FakeView();
  const camera = new CinematicCamera(view);
  camera.enabled = true;
  camera.plan(ShotPlan.of(SEGMENTS, FRAMES_PER_SECOND));
  const robot = new THREE.Vector3();
  const milk = new THREE.Vector3(0.6, 0.2, 0.9);
  camera.update(10, robot, (key) => (key === 'milk' ? milk : null));
  assert.deepEqual(view.controls.target.toArray(), milk.toArray());
  assert.ok(Math.abs(view.camera.position.distanceTo(milk) - Framing.CLOSE_DISTANCE) < 1e-9);
  const seen = Math.atan2(view.camera.position.y - milk.y, view.camera.position.x - milk.x);
  const beside = Math.atan2(milk.y - robot.y, milk.x - robot.x) + Framing.CLOSE_SIDE;
  assert.ok(Math.abs(Math.atan2(Math.sin(seen - beside), Math.cos(seen - beside))) < 1e-9, 'the close-up looks from beyond the object, not from inside the robot');
  const before = view.camera.position.clone();
  camera.update(30, robot, () => null);
  const wide = view.camera.position.distanceTo(before);
  assert.ok(wide > 0 && view.camera.position.distanceTo(robot) < Framing.WIDE_DISTANCE + 1, 'the next pose eases from the last one');
  camera.cut();
  camera.update(30, robot, () => null);
  const look = robot.clone().add(new THREE.Vector3(0, 0, Framing.ROBOT_LOOK_HEIGHT));
  assert.ok(Math.abs(view.camera.position.distanceTo(look) - Framing.WIDE_DISTANCE) < 1e-9, 'after a cut the pose jumps to its shot');
});
