import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  DrawerKey,
  DriveDirection,
  ThreadKey,
  ThreadState,
  WorkshopAction,
  WorkshopBodyKey,
  WorkshopCommandKey,
  WorkshopKey,
  WorkshopStateKey,
  WorkshopView,
} from '../../../protocol.js';
import { QUATERNION_START, multiply, aboutAxis } from '../pose-math.js';
import {
  AlignmentKind,
  Manipulation,
  WorkshopController,
  WorkshopMessage,
} from '../workshop-controller.js';
import { FakeClient, FakeClock, FakeScene, STATE, WORKSHOP, refused } from './fakes.mjs';

/**
 * A controller over the fake contact world.
 */
class ControllerSetup {
  constructor() {
    this.client = new FakeClient();
    this.scene = new FakeScene();
    this.clock = new FakeClock();
    this.controller = new WorkshopController(WORKSHOP, this.scene, this.client, this.clock);
  }

  /**
   * @returns {Array<string>} The actions sent, in order.
   */
  actions() {
    return this.client.commands.map((command) => command[WorkshopCommandKey.ACTION]);
  }
}

const SCREW = WORKSHOP[WorkshopKey.PARTS][0][WorkshopBodyKey.KEY];
const DRIVER = WORKSHOP[WorkshopKey.DRIVER][WorkshopBodyKey.KEY];

// %% state

test('every movable body of the workshop can be chosen, the first one first', () => {
  const { controller } = new ControllerSetup();
  const expected = [
    ...WORKSHOP[WorkshopKey.PARTS],
    ...WORKSHOP[WorkshopKey.BINS],
    WORKSHOP[WorkshopKey.ASSEMBLY],
    WORKSHOP[WorkshopKey.DRIVER],
  ].map((body) => body[WorkshopBodyKey.KEY]);
  assert.deepEqual([...controller.labels.keys()], expected);
  assert.equal(controller.selected, expected[0]);
  assert.equal(controller.select('workshop_environment'), false);
});

test('starting pauses the playback and lets time pass', async () => {
  const setup = new ControllerSetup();
  const outcome = await setup.controller.start();
  assert.equal(outcome.ok, true);
  assert.equal(setup.scene.pauses, 1);
  assert.equal(setup.controller.isRunning(), true);
  assert.deepEqual(setup.scene.shown.at(-1), setup.client.current);
});

test('a state the workshop marks unavailable shows its error', () => {
  const setup = new ControllerSetup();
  const reason = 'The contact world needs mujoco.';
  setup.controller.accept({ ...STATE, [WorkshopStateKey.AVAILABLE]: false, [WorkshopStateKey.ERROR]: reason });
  assert.equal(setup.controller.error, reason);
  assert.equal(setup.controller.isReady(), false);
});

test('a refused command reports the reason the viewer gave', async () => {
  const setup = new ControllerSetup();
  const reason = 'Start the workshop physics first.';
  setup.client.failure = refused(409, reason);
  const outcome = await setup.controller.release();
  assert.equal(outcome.ok, false);
  assert.equal(setup.controller.message, reason);
});

test('a state read sent before a command is not shown after it', async () => {
  const setup = new ControllerSetup();
  const polled = setup.controller.poll();
  const commanded = setup.controller.start();
  await Promise.all([polled, commanded]);
  assert.equal(setup.scene.shown.length, 1);
  assert.equal(setup.controller.isRunning(), true);
});

test('no state is read while a command is under way', async () => {
  const setup = new ControllerSetup();
  const commanded = setup.controller.start();
  await setup.controller.poll();
  await commanded;
  assert.equal(setup.client.stateReads, 0);
});

// %% manipulation

test('grabbing holds the selected body at its measured pose', async () => {
  const setup = new ControllerSetup();
  await setup.controller.start();
  const outcome = await setup.controller.grab();
  assert.equal(outcome.ok, true);
  assert.equal(setup.controller.held(), SCREW);
  assert.deepEqual(setup.controller.target, STATE[WorkshopStateKey.OBJECTS][SCREW]);
});

test('nothing is grabbed before time passes', async () => {
  const setup = new ControllerSetup();
  const outcome = await setup.controller.grab();
  assert.equal(outcome.message, WorkshopMessage.GRAB_FIRST);
  assert.deepEqual(setup.client.commands, []);
});

test('moving shifts the spring target and tilting turns it', async () => {
  const setup = new ControllerSetup();
  await setup.controller.start();
  await setup.controller.grab();
  const start = setup.controller.target.slice();
  await setup.controller.moveBy([0, 0, Manipulation.MOVE_STEP]);
  const moved = setup.client.commands.at(-1)[WorkshopCommandKey.POSE];
  assert.equal(moved[2], Number((start[2] + Manipulation.MOVE_STEP).toFixed(Manipulation.TARGET_DECIMALS)));
  await setup.controller.tilt(2, Manipulation.ANGLE_STEP);
  const tilted = setup.client.commands.at(-1)[WorkshopCommandKey.POSE];
  assert.deepEqual(tilted.slice(QUATERNION_START), multiply(aboutAxis(2, Manipulation.ANGLE_STEP), moved.slice(QUATERNION_START)));
});

test('moving without a held body sends nothing', async () => {
  const setup = new ControllerSetup();
  await setup.controller.start();
  const outcome = await setup.controller.moveBy([0, 0, Manipulation.MOVE_STEP]);
  assert.equal(outcome.ok, false);
  assert.deepEqual(setup.actions(), [WorkshopAction.START]);
});

test('a drawer command names the drawer joint and its target', async () => {
  const setup = new ControllerSetup();
  const drawer = WORKSHOP[WorkshopKey.DRAWERS][0];
  await setup.controller.setDrawer(drawer, drawer[DrawerKey.OPEN]);
  const command = setup.client.commands.at(-1);
  assert.equal(command[WorkshopCommandKey.JOINT], drawer[DrawerKey.JOINT]);
  assert.equal(command[WorkshopCommandKey.POSITION], drawer[DrawerKey.OPEN]);
});

test('driving names its direction', async () => {
  const setup = new ControllerSetup();
  const outcome = await setup.controller.drive(DriveDirection.STOP);
  assert.equal(setup.client.commands.at(-1)[WorkshopCommandKey.DIRECTION], DriveDirection.STOP);
  assert.equal(outcome.message, WorkshopMessage.DRIVER_STOPPED);
});

test('commands are sent in the order they were given', async () => {
  const setup = new ControllerSetup();
  await Promise.all([setup.controller.start(), setup.controller.pause(), setup.controller.reset()]);
  assert.deepEqual(setup.actions(), [WorkshopAction.START, WorkshopAction.PAUSE, WorkshopAction.RESET]);
  assert.equal(setup.controller.pending, 0);
});

// %% alignment

test('positioning a screw brings it to the pilot hole and lets the thread capture it', async () => {
  const setup = new ControllerSetup();
  await setup.controller.start();
  const outcome = await setup.controller.align(AlignmentKind.SCREW);
  assert.equal(outcome.message, WorkshopMessage.SCREW_SEATED);
  const poses = setup.client.commands
    .filter((command) => command[WorkshopCommandKey.ACTION] === WorkshopAction.MOVE)
    .map((command) => command[WorkshopCommandKey.POSE]);
  assert.deepEqual(poses.at(-1), STATE[WorkshopStateKey.THREAD][ThreadKey.SCREW_TARGET_POSE]);
  assert.ok(poses[0][2] >= WORKSHOP[WorkshopKey.LIFT_HEIGHT]);
  assert.equal(setup.actions().at(-1), WorkshopAction.RELEASE);
  assert.equal(setup.client.current[WorkshopStateKey.THREAD][ThreadKey.STATE], ThreadState.SEATED);
});

test('aligning the driver ends with its blade engaged', async () => {
  const setup = new ControllerSetup();
  await setup.controller.start();
  const outcome = await setup.controller.align(AlignmentKind.DRIVER);
  assert.equal(outcome.message, WorkshopMessage.DRIVER_CONTACT);
  assert.equal(setup.controller.held(), DRIVER);
});

test('a body that never reaches its waypoint stops the alignment', async () => {
  const setup = new ControllerSetup();
  await setup.controller.start();
  setup.client.frozen = true;
  const outcome = await setup.controller.align(AlignmentKind.SCREW);
  assert.equal(outcome.message, WorkshopMessage.BLOCKED);
  assert.equal(setup.controller.aligning, false);
});

test('only a screw is positioned in the pilot hole', async () => {
  const setup = new ControllerSetup();
  await setup.controller.start();
  setup.controller.select(DRIVER);
  const outcome = await setup.controller.align(AlignmentKind.SCREW);
  assert.equal(outcome.message, WorkshopMessage.SELECT_SCREW);
});

// %% views and closing

test('a named view moves the camera', () => {
  const setup = new ControllerSetup();
  assert.equal(setup.controller.look(WorkshopView.BENCH).ok, true);
  assert.deepEqual(setup.scene.views, [WORKSHOP[WorkshopKey.CAMERAS][WorkshopView.BENCH]]);
  assert.equal(setup.controller.look('ceiling').ok, false);
});

test('closing lets go of a held body and shows nothing more', async () => {
  const setup = new ControllerSetup();
  await setup.controller.start();
  await setup.controller.grab();
  const shown = setup.scene.shown.length;
  await setup.controller.close();
  assert.equal(setup.actions().at(-1), WorkshopAction.RELEASE);
  setup.controller.accept(STATE);
  assert.equal(setup.scene.shown.length, shown);
});
