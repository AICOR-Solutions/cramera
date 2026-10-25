import assert from 'node:assert/strict';
import { test } from 'node:test';

import { EventBus } from 'cramera-viewer/core/event-bus.js';
import { LaboratoryCatalogKey, LaboratoryName, LaboratoryRoute, TaskRunState, ViewerEvent, ViewerRoute } from 'cramera-viewer/protocol.js';

import { connectLaboratory } from '../../src/cramera_laboratory/web/index.js';
import { Text } from '../../src/cramera_laboratory/web/laboratory-panel.js';
import { FakeApi, FakeFetch, FakeTimer, FakeView } from './fakes.mjs';
import { FakeDocument } from 'cramera-testing/fake-document.mjs';

const routeUrl = (route) => `http://viewer${ViewerRoute.PLUGIN_API}${LaboratoryName.PLUGIN}/${route}`;
const LABORATORY = 'aicor_medical_lab';
async function connected(state = TaskRunState.IDLE) {
  const document = new FakeDocument();
  const api = new FakeApi();
  api.answers.set(routeUrl(LaboratoryRoute.LABORATORIES), {
    [LaboratoryCatalogKey.LABORATORIES]: [{ name: LABORATORY, title: 'AICOR Laboratory', installed: false, instruments: 0 }],
    [LaboratoryCatalogKey.PHYSICS_AVAILABLE]: true,
  });
  api.answers.set(routeUrl(LaboratoryRoute.DEVICES), { devices: [] });
  api.answers.set(routeUrl(LaboratoryRoute.TRANSFER_STATE), { state, scene: 'aicor_medical_lab_pr2_transfer' });
  const network = new FakeFetch();
  network.answer(routeUrl(LaboratoryRoute.INSTALL), 200, { scene: LABORATORY });
  const bus = new EventBus();
  const requested = [];
  const view = new FakeView();
  const timer = new FakeTimer();
  const transfers = [];
  const parts = await connectLaboratory({ bus, api, view }, (name) => requested.push(name), document, timer, (url, options) => network.fetch(url, options), () => {}, (run) => transfers.push(run));
  return { parts, requested, document, bus, view, timer, api, transfers };
}

async function open(parts) {
  parts.panel.laboratories.findAll((child) => child.tagName === 'BUTTON' && child.textContent === Text.OPEN)[0].click();
  await new Promise((resolve) => setImmediate(resolve));
}

test('the page connects its controls without needing a viewer panel host', async () => {
  const { parts } = await connected();
  assert.equal(parts.panel.panel.title, 'Medical lab');
  assert.ok(parts.panel.laboratories.innerText.includes(Text.LABORATORIES));
  parts.dispose();
});

test('a newly installed scene opens through the page without requiring an old scene index', async () => {
  const { parts, requested } = await connected();
  await open(parts);
  assert.deepEqual(requested, [LABORATORY]);
  parts.dispose();
});

test('leaving the page cancels transfer polling and removes pointer handlers', async () => {
  const { parts, timer, view } = await connected(TaskRunState.RUNNING);
  const handle = timer.calls.length;
  parts.dispose();
  assert.ok(timer.cancelled.includes(handle));
  assert.ok([...view.renderer.domElement.listeners.values()].every((listeners) => listeners.size === 0));
});

test('loading a scene hides the simulation controls', async () => {
  const { parts, bus } = await connected();
  bus.publish(ViewerEvent.SCENE_LOADING, 'kitchen');
  assert.equal(parts.panel.objectChoice, null);
  parts.dispose();
});

test('a temporary transfer connection failure recovers and still reports the saved recording', async () => {
  const { parts, timer, api, transfers } = await connected(TaskRunState.RUNNING);
  api.answers.set(routeUrl(LaboratoryRoute.TRANSFER_STATE), new Error('Connection interrupted'));
  await timer.runLatest();
  assert.ok(parts.panel.message.textContent.includes('Connection interrupted'));
  assert.equal(timer.calls.length, 2);
  api.answers.set(routeUrl(LaboratoryRoute.TRANSFER_STATE), { state: TaskRunState.RECORDED, scene: 'finished-pr2' });
  await timer.runLatest();
  assert.equal(transfers.at(-1).scene, 'finished-pr2');
  assert.equal(parts.panel.message.textContent, '');
  assert.ok(parts.panel.demos.innerText.includes(Text.OPEN_RECORDING));
  parts.dispose();
});
