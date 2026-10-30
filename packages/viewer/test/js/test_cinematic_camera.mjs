import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import { SegmentKey } from '../../src/cramera/web/protocol.js';
import { CinematicCamera, CloseUp, Framing, LineOfSight, REFERENCE_DURATION, SHORTEST_TIMING, ShotPlan, ShotTiming, Sight, SLOW_MOTION, smoothstep } from '../../src/cramera/web/scene/cinematic-camera.js';

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

/**
 * @param {Array<number>} min One corner of the box.
 * @param {Array<number>} max The opposite corner.
 * @param {THREE.Material=} material What the box is drawn with.
 * @returns {THREE.Mesh} A box between the corners, such as a wall or a cabinet.
 */
function block(min, max, material = new THREE.MeshBasicMaterial()) {
  const size = max.map((value, axis) => value - min[axis]);
  const box = new THREE.Mesh(new THREE.BoxGeometry(...size), material);
  box.position.set(...max.map((value, axis) => (value + min[axis]) / 2));
  box.updateMatrixWorld();
  return box;
}

/**
 * @param {FakeView} view The view the camera drives.
 * @param {Array<THREE.Object3D>} obstacles The scene's geometry.
 * @param {THREE.Vector3=} subject What the camera films, by default what it looks at.
 * @returns {boolean} Whether anything of the geometry stands between the camera and
 *   the subject.
 */
function hidden(view, obstacles, subject = view.controls.target) {
  const toward = new THREE.Vector3().subVectors(subject, view.camera.position);
  const raycaster = new THREE.Raycaster(view.camera.position, toward.clone().normalize(), 0, toward.length());
  const twoSided = obstacles.map((obstacle) => {
    const copy = new THREE.Mesh(obstacle.geometry, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }));
    copy.matrixWorld.copy(obstacle.matrixWorld);
    return copy;
  });
  return raycaster.intersectObjects(twoSided, false).length > 0;
}

/**
 * @param {FakeView} view The view the camera drives.
 * @returns {number} The direction the camera looks from, around what it looks at.
 */
function azimuthOf(view) {
  return Math.atan2(view.camera.position.y - view.controls.target.y, view.camera.position.x - view.controls.target.x);
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

// %% clear view

test('a line of sight reaches up to the nearest surface, keeping a margin, and ignores what is not drawn', () => {
  const subject = new THREE.Vector3(0, 0, 1);
  const east = new THREE.Vector3(1, 0, 0);
  assert.equal(new LineOfSight().reach(subject, east, 3), 3, 'nothing stands in the way of a camera in an empty scene');
  const wall = block([2, -5, 0], [2.1, 5, 3]);
  const sight = new LineOfSight([wall]);
  assert.ok(Math.abs(sight.reach(subject, east, 3) - (2 - Sight.MARGIN)) < 1e-9);
  assert.equal(sight.reach(subject, east, 1.5), 1.5, 'a wall behind the camera does not matter');
  assert.ok(Math.abs(new LineOfSight([block([0.1, -5, 0], [0.2, 5, 3])]).reach(subject, east, 3) - 0.05) < 1e-9, 'a surface close to the subject leaves the camera half the way');
  const flat = new THREE.Mesh(new THREE.PlaneGeometry(10, 10), new THREE.MeshBasicMaterial());
  flat.position.set(2, 0, 0);
  flat.rotation.y = Math.PI / 2;
  flat.updateMatrixWorld();
  assert.ok(new LineOfSight([flat]).reach(subject, east, 3) < 2, 'a one-sided surface stands in the way from both sides');
  wall.visible = false;
  assert.equal(sight.reach(subject, east, 3), 3, 'a hidden wall does not stand in the way');
  const glass = block([2, -5, 0], [2.1, 5, 3], new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.2 }));
  assert.equal(new LineOfSight([glass]).reach(subject, east, 3), 3, 'glass does not stand in the way');
});

test('a mesh of many triangles stands in the way as its box, unless the camera looks from inside it', () => {
  const ball = new THREE.Mesh(new THREE.SphereGeometry(0.5, 64, 64), new THREE.MeshBasicMaterial());
  ball.position.set(2, 0, 1);
  ball.updateMatrixWorld();
  assert.ok(ball.geometry.index.count / 3 > Sight.SOLID_TRIANGLES);
  const sight = new LineOfSight([ball]);
  const east = new THREE.Vector3(1, 0, 0);
  const past = new THREE.Vector3(0, 0.49, 1.49);
  assert.ok(Math.abs(sight.reach(past, east, 3) - (1.5 - Sight.MARGIN)) < 1e-9, 'a ray past the ball but through its box is blocked by the box');
  const inside = new THREE.Vector3(1.6, 0.49, 1.49);
  assert.equal(sight.reach(inside, east, 3), 3, 'a ray from inside the box tests the ball itself');
  const facing = new THREE.Vector3(1.55, 0.3, 1.3);
  const surface = 2 - Math.sqrt(0.25 - 0.3 ** 2 - 0.3 ** 2) - facing.x;
  assert.ok(Math.abs(sight.reach(facing, east, 3) - surface / 2) < 0.005, 'and finds the ball where it is');
  ball.position.set(2, 0, 3);
  ball.updateMatrixWorld();
  sight.refresh();
  assert.equal(sight.reach(facing, east, 3), 3, 'and where it moved to');
});

test('a ray from inside a mesh of many triangles tests only the triangles near it', () => {
  const ball = new THREE.Mesh(new THREE.SphereGeometry(0.5, 256, 256), new THREE.MeshBasicMaterial());
  ball.position.set(2, 0, 1);
  ball.updateMatrixWorld();
  const sight = new LineOfSight([ball]);
  const facing = new THREE.Vector3(1.55, 0.3, 1.3);
  const east = new THREE.Vector3(1, 0, 0);
  sight.reach(facing, east, 3);
  const start = performance.now();
  for (let ray = 0; ray < 100; ray += 1) sight.reach(facing, new THREE.Vector3(1, 0.01 * ray - 0.5, 0).normalize(), 3);
  assert.ok(performance.now() - start < 50, `a hundred rays through ${ball.geometry.index.count / 3} triangles take ${performance.now() - start} ms`);
});

test('a wall between the robot and the wide shot sends the camera round to a clear side', () => {
  const view = new FakeView();
  const camera = new CinematicCamera(view);
  camera.enabled = true;
  camera.plan(ShotPlan.of(SEGMENTS, FRAMES_PER_SECOND));
  const wall = block([1.5, -5, 0], [1.6, 5, 3]);
  camera.setObstacles([wall]);
  camera.update(0, new THREE.Vector3(), () => null);
  assert.equal(hidden(view, [wall]), false, 'the robot is in sight');
  assert.ok(Math.abs(view.camera.position.distanceTo(view.controls.target) - Framing.WIDE_DISTANCE) < 1e-9, 'the camera keeps its distance rather than moving up to the wall');
  assert.ok(view.camera.position.x < 1.5, 'the camera stands in front of the wall');
});

test('in a closed room the camera moves in front of the wall rather than film it', () => {
  const view = new FakeView();
  const camera = new CinematicCamera(view);
  camera.enabled = true;
  const room = [
    block([-1.3, -1.3, -0.1], [1.3, 1.3, 0]),
    block([-1.3, -1.3, 2.4], [1.3, 1.3, 2.5]),
    block([1.2, -1.3, 0], [1.3, 1.3, 2.4]),
    block([-1.3, -1.3, 0], [-1.2, 1.3, 2.4]),
    block([-1.3, 1.2, 0], [1.3, 1.3, 2.4]),
    block([-1.3, -1.3, 0], [1.3, -1.2, 2.4]),
  ];
  camera.setObstacles(room);
  camera.update(0, new THREE.Vector3(), () => null);
  assert.equal(hidden(view, room), false);
  assert.ok(view.camera.position.distanceTo(view.controls.target) < Framing.WIDE_DISTANCE);
  assert.ok(Math.abs(view.camera.position.x) < 1.2 && Math.abs(view.camera.position.y) < 1.2 && view.camera.position.z < 2.4, 'the camera is inside the room');
});

test('the wide orbit turns back where a wall would come between the camera and the robot', () => {
  const view = new FakeView();
  const camera = new CinematicCamera(view);
  camera.enabled = true;
  const wall = block([-1.6, -5, 0], [-1.5, 5, 3]);
  camera.setObstacles([wall]);
  const robot = new THREE.Vector3();
  let previous = null;
  let farthest = 0;
  for (let step = 0; step <= 600; step += 1) {
    camera.update(step / 10, robot, () => null);
    assert.equal(hidden(view, [wall]), false, `the robot is in sight at ${step / 10} s`);
    if (previous) assert.ok(view.camera.position.distanceTo(previous) < 0.2, `the camera glides at ${step / 10} s`);
    previous = view.camera.position.clone();
    farthest = Math.max(farthest, azimuthOf(view));
  }
  assert.ok(farthest > 1.5 && farthest < Math.PI - 0.5, 'the orbit went round as far as the wall let it');
  assert.ok(azimuthOf(view) < farthest - 1, 'and came back');
});

test('a close-up whose side is behind a cabinet films from the other side', () => {
  const view = new FakeView();
  const camera = new CinematicCamera(view);
  camera.enabled = true;
  camera.plan(ShotPlan.of(SEGMENTS, FRAMES_PER_SECOND));
  const panel = block([0.5, 0.25, 0], [2, 0.35, 2]);
  camera.setObstacles([panel]);
  const milk = new THREE.Vector3(0.6, 0, 0.9);
  camera.update(10, new THREE.Vector3(), (key) => (key === 'milk' ? milk : null));
  assert.deepEqual(view.controls.target.toArray(), milk.toArray());
  assert.equal(hidden(view, [panel]), false);
  assert.ok(Math.abs(view.camera.position.distanceTo(milk) - Framing.CLOSE_DISTANCE) < 1e-9);
  assert.ok(view.camera.position.y < 0, 'the camera films from the side away from the panel');
});

test('a view through a narrow opening counts as blocked', () => {
  const view = new FakeView();
  const camera = new CinematicCamera(view);
  camera.enabled = true;
  const wall = [block([1.5, -5, 0], [1.6, -0.3, 3]), block([1.5, 0.3, 0], [1.6, 5, 3]), block([1.5, -0.3, 2.5], [1.6, 0.3, 3])];
  camera.setObstacles(wall);
  camera.update(0, new THREE.Vector3(), () => null);
  assert.equal(hidden(view, wall), false);
  assert.ok(view.camera.position.x < 1.5, 'the camera does not look through the opening');
});

test('a wall that comes between the gliding camera and the robot moves the camera in front of it at once', () => {
  const view = new FakeView();
  const camera = new CinematicCamera(view);
  camera.enabled = true;
  const robot = new THREE.Vector3();
  camera.update(0, robot, () => null);
  const wall = block([2.4, -5, 0], [2.5, 5, 4]);
  camera.setObstacles([wall]);
  camera.update(0.1, robot, () => null);
  assert.equal(hidden(view, [wall]), false);
  assert.ok(view.camera.position.x < 2.4);
});

test('a robot that moves behind a wall faster than the camera eases after it is cut to', () => {
  const view = new FakeView();
  const camera = new CinematicCamera(view);
  camera.enabled = true;
  const wall = block([0.5, 1.4, 0], [5, 1.5, 4]);
  camera.setObstacles([wall]);
  camera.update(0, new THREE.Vector3(), () => null);
  const robot = new THREE.Vector3(0, 3, 0);
  camera.update(0.1, robot, () => null);
  const chest = robot.clone().add(new THREE.Vector3(0, 0, Framing.ROBOT_LOOK_HEIGHT));
  assert.equal(hidden(view, [wall], chest), false, 'the robot is in sight');
  assert.deepEqual(view.controls.target.toArray(), chest.toArray(), 'the camera cut to the robot');
});
