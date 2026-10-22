import { test } from 'node:test';
import assert from 'node:assert/strict';

import { EventBus } from '../../../core/event-bus.js';
import { PanelHost } from '../../../panels/panel-host.js';
import {
  AssetRightsKey,
  DrawerKey,
  ErrorKey,
  IndexEntryKey,
  IndexKey,
  SelectionKey,
  SelectionKind,
  ThreadKey,
  ViewerEvent,
  WorkshopAction,
  WorkshopBodyKey,
  WorkshopCommandKey,
  WorkshopKey,
  WorkshopSceneKey,
  WorkshopStateKey,
} from '../../../protocol.js';
import { WorkshopClient } from '../workshop-client.js';
import { Manipulation, WorkshopController } from '../workshop-controller.js';
import { WorkshopPanel, rightsElement } from '../workshop-panel.js';
import { IDLE_TEXT, PANEL, WorkshopModule, register } from '../index.js';
import { FakeAnswer, FakeClient, FakeScene, FakeTimers, SCENE, STATE, WORKSHOP } from './fakes.mjs';
import { FakeDocument } from './support/fake-document.mjs';

/**
 * @param {Object} element An element.
 * @param {string} text A button's text.
 * @returns {Object} The first button with that text.
 */
function button(element, text) {
  return element.findAll((child) => child.tagName === 'BUTTON' && child.textContent === text)[0];
}

/**
 * A panel over the fake contact world.
 */
class PanelSetup {
  constructor() {
    this.document = new FakeDocument();
    this.client = new FakeClient();
    this.controller = new WorkshopController(WORKSHOP, new FakeScene(), this.client);
    this.demos = 0;
    this.panel = new WorkshopPanel(this.document, WORKSHOP, this.controller, SCENE[WorkshopSceneKey.ASSET_RIGHTS], () => {
      this.demos += 1;
    });
  }
}

// %% panel

test('before the world answers only starting is possible', () => {
  const { panel } = new PanelSetup();
  assert.equal(button(panel.element, 'Start physics').disabled, false);
  assert.equal(button(panel.element, 'Grab selected').disabled, true);
  assert.equal(button(panel.element, 'Reset').disabled, true);
});

test('a running world offers grabbing and pausing', async () => {
  const setup = new PanelSetup();
  await setup.controller.start();
  assert.equal(setup.panel.run.textContent, 'Pause physics');
  assert.equal(button(setup.panel.element, 'Grab selected').disabled, false);
  assert.equal(button(setup.panel.element, 'Release').disabled, true);
});

test('each drawer offers to close once it is open', () => {
  const setup = new PanelSetup();
  setup.controller.accept(STATE);
  const drawers = setup.panel.element.findAll((child) => (child.className ?? '').includes('workshop-drawer'));
  const labels = drawers.map((row) => row.children[1].textContent);
  const expected = WORKSHOP[WorkshopKey.DRAWERS].map((drawer) =>
    STATE[WorkshopStateKey.JOINTS][drawer[DrawerKey.JOINT]] > drawer[DrawerKey.OPEN] / 2 ? 'Close' : 'Open',
  );
  assert.deepEqual(labels, expected);
});

test('the thread, the held body and the contacts are shown', () => {
  const setup = new PanelSetup();
  setup.controller.accept({ ...STATE, [WorkshopStateKey.HELD]: WORKSHOP[WorkshopKey.DRIVER][WorkshopBodyKey.KEY] });
  assert.match(setup.panel.observation.textContent, new RegExp(WORKSHOP[WorkshopKey.DRIVER][WorkshopBodyKey.LABEL]));
  assert.match(setup.panel.observation.textContent, new RegExp(String(STATE[WorkshopStateKey.CONTACTS].length)));
  assert.match(setup.panel.threadState.textContent, new RegExp(STATE[WorkshopStateKey.THREAD][ThreadKey.STATE]));
});

test('a pressed button shows what its command came to', async () => {
  const setup = new PanelSetup();
  button(setup.panel.element, 'Start physics').dispatch('click');
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(setup.client.commands.length, 1);
  assert.equal(setup.panel.status.textContent, setup.controller.message);
});

test('the asset rights name the author and the permission terms', () => {
  const rights = SCENE[WorkshopSceneKey.ASSET_RIGHTS];
  const element = rightsElement(new FakeDocument(), rights);
  assert.match(element.innerText, new RegExp(rights[AssetRightsKey.PRINCIPAL_AUTHOR]));
  assert.ok(element.innerText.includes(rights[AssetRightsKey.PERMISSION_NOTICE]));
});

test('the recorded demo is offered only when it is there', () => {
  const setup = new PanelSetup();
  assert.equal(setup.panel.demo.hidden, true);
  setup.panel.offerDemo(true);
  assert.equal(setup.panel.demo.hidden, false);
  setup.panel.demo.dispatch('click');
  assert.equal(setup.demos, 1);
});

// %% module

/**
 * The module in a viewer context with fake routes.
 */
class ModuleSetup {
  /**
   * @param {Array<string>} scenes The names the scenes index lists.
   */
  constructor(scenes = []) {
    this.document = new FakeDocument();
    this.document.head = this.document.createElement('head');
    this.bus = new EventBus();
    this.panels = new PanelHost(this.document.createElement('aside'));
    this.timers = new FakeTimers();
    this.client = new FakeClient();
    this.requested = [];
    this.bus.subscribe(ViewerEvent.SCENE_REQUESTED, (name) => this.requested.push(name));
    const api = {
      url: (route) => `http://127.0.0.1${route}`,
      scenes: async () => ({ [IndexKey.SCENES]: scenes.map((name) => ({ [IndexEntryKey.NAME]: name })) }),
    };
    const view = { requestRender() {}, camera: { position: { set() {} } }, controls: { target: { set() {} }, update() {} } };
    this.context = { bus: this.bus, panels: this.panels, api, view };
    this.module = new WorkshopModule(this.context, this.document, this.timers, this.client);
  }

  /**
   * @param {Object} description A scene description.
   * @returns {Object} A loaded scene that records what is put on it.
   */
  loaded(description) {
    this.poses = [];
    this.joints = [];
    return {
      description,
      objects: { setPoses: (poses) => this.poses.push(poses) },
      models: { setJointValues: (values) => this.joints.push(values) },
    };
  }
}

test('a scene without a workshop shows what the panel is for', () => {
  const setup = new ModuleSetup();
  assert.equal(setup.module.panel.element.innerText, IDLE_TEXT);
  assert.equal(setup.module.panel.identifier, PANEL.IDENTIFIER);
});

test('a workshop scene starts its world and polls it', async () => {
  const setup = new ModuleSetup();
  await setup.module.enter(setup.loaded(SCENE));
  assert.ok(setup.module.controller);
  assert.deepEqual([...setup.timers.intervals.values()].map((interval) => interval.milliseconds), [Manipulation.POLL_MILLISECONDS]);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(setup.module.controller.isRunning(), true);
  const shownJoints = setup.joints.at(-1);
  assert.equal(shownJoints.size, 1);
  assert.equal(setup.poses.at(-1).size, Object.keys(STATE[WorkshopStateKey.OBJECTS]).length);
});

test('leaving a workshop scene stops polling and lets go', async () => {
  const setup = new ModuleSetup();
  await setup.module.enter(setup.loaded(SCENE));
  await new Promise((resolve) => setImmediate(resolve));
  setup.bus.publish(ViewerEvent.SCENE_LOADING, 'other');
  assert.equal(setup.timers.intervals.size, 0);
  assert.equal(setup.module.controller, null);
  assert.equal(setup.module.panel.element.innerText, IDLE_TEXT);
});

test('picking a body in the 3D view selects it in the panel', async () => {
  const setup = new ModuleSetup();
  await setup.module.enter(setup.loaded(SCENE));
  const key = WORKSHOP[WorkshopKey.DRIVER][WorkshopBodyKey.KEY];
  setup.bus.publish(ViewerEvent.ENTITY_SELECTED, { [SelectionKey.KIND]: SelectionKind.OBJECT, [SelectionKey.NAME]: key });
  assert.equal(setup.module.controller.selected, key);
});

test('a recording made in the workshop shows the assets\' rights', async () => {
  const setup = new ModuleSetup();
  await setup.module.enter(setup.loaded({ [WorkshopSceneKey.ASSET_RIGHTS]: SCENE[WorkshopSceneKey.ASSET_RIGHTS] }));
  assert.equal(setup.module.controller, null);
  assert.match(setup.module.panel.element.innerText, new RegExp(SCENE[WorkshopSceneKey.ASSET_RIGHTS][AssetRightsKey.INSTITUTION]));
});

test('the recorded demo the workshop names is offered and opened', async () => {
  const demo = 'aicor_workshop_pr2_assembly';
  const setup = new ModuleSetup([demo]);
  const scene = structuredClone(SCENE);
  scene[WorkshopSceneKey.WORKSHOP][WorkshopKey.DEMO_SCENE] = demo;
  await setup.module.enter(setup.loaded(scene));
  assert.equal(setup.module.content.demo.hidden, false);
  setup.module.content.demo.dispatch('click');
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(setup.requested, [demo]);
});

test('registering adds the panel and its stylesheet', () => {
  const setup = new ModuleSetup();
  const module = register(setup.context, setup.document, setup.timers);
  assert.deepEqual(setup.panels.identifiers(), [PANEL.IDENTIFIER]);
  assert.equal(setup.document.head.children.length, 1);
  assert.ok(module instanceof WorkshopModule);
});

// %% client

test('the client sends commands as JSON to the plugin\'s command route', async () => {
  const requests = [];
  const fetch = async (url, init) => {
    requests.push({ url, init });
    return new FakeAnswer(200, STATE);
  };
  const client = new WorkshopClient(fetch, { url: (route) => `http://127.0.0.1${route}` });
  const command = { [WorkshopCommandKey.ACTION]: WorkshopAction.START };
  assert.deepEqual(await client.command(command), STATE);
  assert.match(requests[0].url, /\/api\/plugins\/workshop\/command$/);
  assert.deepEqual(JSON.parse(requests[0].init.body), command);
  await client.state();
  assert.match(requests[1].url, /\/api\/plugins\/workshop\/state$/);
});

test('the client reports the reason of a refused request', async () => {
  const reason = 'Start the workshop physics first.';
  const fetch = async () => new FakeAnswer(409, { [ErrorKey.ERROR]: reason });
  const client = new WorkshopClient(fetch, { url: (route) => route });
  await assert.rejects(client.state(), (error) => error.reason === reason && error.status === 409);
  const unexplained = new WorkshopClient(async () => new FakeAnswer(500, null, 'text/plain'), { url: (route) => route });
  await assert.rejects(unexplained.state(), (error) => error.reason === 'status 500');
});
