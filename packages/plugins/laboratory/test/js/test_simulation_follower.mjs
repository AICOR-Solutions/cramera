import assert from 'node:assert/strict';
import { test } from 'node:test';

import { EventBus } from 'cramera-viewer/core/event-bus.js';
import { LaboratoryName, LaboratoryRoute, SimulationAnswerKey, SimulationState, SnapshotKey, ViewerEvent, ViewerRoute } from 'cramera-viewer/protocol.js';

import { LaboratoryClient } from '../../src/cramera_laboratory/web/laboratory-client.js';
import { IDLE_INTERVAL, RUNNING_INTERVAL, SimulationFollower } from '../../src/cramera_laboratory/web/simulation-follower.js';
import { FakeApi, FakeLoadedScene, FakeTimer, FakeView, readDataset } from './fakes.mjs';

const SCENE = 'aicor_medical_lab_contact_physics';
const stateUrl = `http://viewer${ViewerRoute.PLUGIN_API}${LaboratoryName.PLUGIN}/${LaboratoryRoute.STATE}`;

function running() {
  return { [SimulationAnswerKey.STATE]: SimulationState.RUNNING, [SimulationAnswerKey.SCENE]: SCENE, [SimulationAnswerKey.SNAPSHOT]: readDataset('snapshot.json') };
}

function setUp(answer = running()) {
  const bus = new EventBus();
  const api = new FakeApi();
  api.answers.set(stateUrl, answer);
  const view = new FakeView();
  const timer = new FakeTimer();
  const answers = [];
  const failures = [];
  const followed = [];
  const follower = new SimulationFollower(bus, view, new LaboratoryClient(() => null, api), timer, (shown) => answers.push(shown), () => followed.push(true), (error) => failures.push(error));
  return { bus, api, view, timer, answers, failures, followed, follower };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));

test('a scene without contact physics is not followed', async () => {
  const { bus, follower, api } = setUp();
  bus.publish(ViewerEvent.SCENE_LOADED, new FakeLoadedScene('kitchen', null));
  await settle();
  assert.equal(follower.scene, null);
  assert.deepEqual(api.requested, []);
});

test('a simulated scene is posed as measured and asked again soon', async () => {
  const { bus, view, timer, answers, followed } = setUp();
  const scene = new FakeLoadedScene(SCENE, readDataset('controls.json'));
  bus.publish(ViewerEvent.SCENE_LOADED, scene);
  await settle();
  const snapshot = readDataset('snapshot.json');
  assert.deepEqual([...scene.posed[0].keys()], Object.keys(snapshot[SnapshotKey.OBJECTS]));
  assert.deepEqual([...scene.jointValues[0].get('laboratory').keys()], Object.keys(snapshot[SnapshotKey.JOINTS]));
  assert.deepEqual(scene.rackJoint.position.toArray(), snapshot[SnapshotKey.BODY_POSES].laboratory_rack.slice(0, 3));
  assert.equal(view.renderer.localClippingEnabled, true);
  assert.ok(view.scene.children.length === 1 && view.renders === 1);
  assert.equal(answers.length, 1);
  assert.deepEqual(followed, [true]);
  assert.equal(timer.calls.at(-1).milliseconds, RUNNING_INTERVAL);
});

test('an idle simulation is asked rarely', async () => {
  const { bus, timer } = setUp({ [SimulationAnswerKey.STATE]: SimulationState.IDLE });
  bus.publish(ViewerEvent.SCENE_LOADED, new FakeLoadedScene(SCENE, readDataset('controls.json')));
  await settle();
  assert.equal(timer.calls.at(-1).milliseconds, IDLE_INTERVAL);
});

test('an answer for another scene does not move this one', async () => {
  const answer = running();
  answer[SimulationAnswerKey.SCENE] = 'another_laboratory_contact_physics';
  const { bus, answers } = setUp(answer);
  const scene = new FakeLoadedScene(SCENE, readDataset('controls.json'));
  bus.publish(ViewerEvent.SCENE_LOADED, scene);
  await settle();
  assert.deepEqual(scene.posed, []);
  assert.deepEqual(answers, []);
});

test('loading another scene drops the drawing and the pending answer', async () => {
  const { bus, view, timer, answers } = setUp();
  bus.publish(ViewerEvent.SCENE_LOADED, new FakeLoadedScene(SCENE, readDataset('controls.json')));
  bus.publish(ViewerEvent.SCENE_LOADING, 'kitchen');
  await settle();
  assert.equal(view.scene.children.length, 0);
  assert.deepEqual(answers, []);
  assert.ok(timer.cancelled.length >= 1);
});

test('a failing request is reported and asked again', async () => {
  const { bus, api, failures, timer } = setUp();
  api.answers.set(stateUrl, new Error('offline'));
  bus.publish(ViewerEvent.SCENE_LOADED, new FakeLoadedScene(SCENE, readDataset('controls.json')));
  await settle();
  assert.equal(failures[0].message, 'offline');
  assert.equal(timer.calls.at(-1).milliseconds, IDLE_INTERVAL);
});

test('disposing removes the subscriptions', () => {
  const { bus, follower } = setUp();
  follower.dispose();
  assert.equal(bus.listenerCount(ViewerEvent.SCENE_LOADED), 0);
});
