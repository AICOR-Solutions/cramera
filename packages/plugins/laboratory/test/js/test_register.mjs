import assert from 'node:assert/strict';
import { test } from 'node:test';

import { EventBus } from 'cramera-viewer/core/event-bus.js';
import { PanelHost } from 'cramera-viewer/panels/panel-host.js';
import { LaboratoryCatalogKey, LaboratoryName, LaboratoryRoute, TaskRunState, ViewerEvent, ViewerRoute } from 'cramera-viewer/protocol.js';

import { register } from '../../src/cramera_laboratory/web/index.js';
import { Text } from '../../src/cramera_laboratory/web/laboratory-panel.js';
import { FakeApi, FakeFetch, FakeTimer, FakeView } from './fakes.mjs';
import { FakeDocument } from './support/fake-document.mjs';

const routeUrl = (route) => `http://viewer${ViewerRoute.PLUGIN_API}${LaboratoryName.PLUGIN}/${route}`;
const LABORATORY = 'aicor_medical_lab';
const PAGE = 'http://viewer/index.html?scene=kitchen';

async function registered(listed) {
  const document = new FakeDocument();
  const api = new FakeApi(listed);
  api.answers.set(routeUrl(LaboratoryRoute.LABORATORIES), {
    [LaboratoryCatalogKey.LABORATORIES]: [{ name: LABORATORY, title: 'AICOR Laboratory', installed: false, instruments: 0 }],
    [LaboratoryCatalogKey.PHYSICS_AVAILABLE]: true,
  });
  api.answers.set(routeUrl(LaboratoryRoute.DEVICES), { devices: [] });
  api.answers.set(routeUrl(LaboratoryRoute.TRANSFER_STATE), { state: TaskRunState.IDLE, scene: 'aicor_medical_lab_pr2_transfer' });
  const network = new FakeFetch();
  network.answer(routeUrl(LaboratoryRoute.INSTALL), 200, { scene: LABORATORY });
  const bus = new EventBus();
  const panels = new PanelHost(document.createElement('aside'));
  const location = { href: PAGE, assigned: [], assign(href) { this.assigned.push(href); } };
  const requested = [];
  bus.subscribe(ViewerEvent.SCENE_REQUESTED, (name) => requested.push(name));
  const parts = await register({ bus, panels, api, view: new FakeView() }, document, new FakeTimer(), location, (url, options) => network.fetch(url, options));
  return { parts, panels, location, requested, document, bus };
}

async function open(parts) {
  parts.panel.laboratories.findAll((child) => child.tagName === 'BUTTON' && child.textContent === Text.OPEN)[0].click();
  await new Promise((resolve) => setImmediate(resolve));
}

test('registering adds the panel and its stylesheet', async () => {
  const { panels, document } = await registered([]);
  assert.deepEqual(panels.identifiers(), [LaboratoryName.PLUGIN]);
  assert.ok(document.head.children[0].href.endsWith('laboratory.css'));
});

test('a scene the page lists is requested from the viewer', async () => {
  const { parts, requested, location } = await registered([LABORATORY]);
  await open(parts);
  assert.deepEqual(requested, [LABORATORY]);
  assert.deepEqual(location.assigned, []);
});

test('a scene the page does not list loads the page anew', async () => {
  const { parts, requested, location } = await registered([]);
  await open(parts);
  assert.deepEqual(requested, []);
  assert.deepEqual(location.assigned, [`http://viewer/index.html?scene=${LABORATORY}`]);
});

test('loading a scene hides the simulation controls', async () => {
  const { parts, bus } = await registered([]);
  bus.publish(ViewerEvent.SCENE_LOADING, 'kitchen');
  assert.equal(parts.panel.objectChoice, null);
});
