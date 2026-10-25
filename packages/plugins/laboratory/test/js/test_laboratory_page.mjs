import assert from 'node:assert/strict';
import { test } from 'node:test';

import { FakeDocument } from 'cramera-testing/fake-document.mjs';
import { ViewerApi } from 'cramera-viewer/core/viewer-api.js';
import { LaboratoryRoute, LiveInfoKey, LiveRoute, LiveStateKey, TaskRunKey, TaskRunState } from 'cramera-viewer/protocol.js';
import { LaboratoryPage, viewerRootOf } from '../../src/cramera_laboratory/web/laboratory-page.js';
import { Text } from '../../src/cramera_laboratory/web/laboratory-panel.js';
import { FakeTimer, FakeView } from './fakes.mjs';

const PAGE = 'http://viewer/demo/plugins/laboratory/laboratory.html';
const PREVIEW = 'aicor_medical_lab_pr2';

function environment({ previewAvailable = true, transfer = TaskRunState.UNAVAILABLE } = {}) {
  const document = new FakeDocument();
  const root = document.createElement('main');
  const requested = [];
  const scenes = [];
  const states = [];
  const frames = [];
  const intervals = new Map();
  const timers = { setInterval(callback, milliseconds) { intervals.set(milliseconds, callback); return milliseconds; }, clearInterval(handle) { intervals.delete(handle); } };
  const location = { href: PAGE };
  const history = { replaceState(_state, _title, url) { location.href = url.href; } };
  const view = new FakeView();
  view.start = (tick) => { view.tick = tick; };
  view.dispose = () => { view.disposed = true; };
  const fetch = async (url, options = {}) => {
    requested.push({ url, options });
    if (url.includes('/transfer/live/')) {
      const route = url.split('/transfer/live')[1];
      const answer = route === LiveRoute.INFO
        ? { [LiveInfoKey.BUNDLE_SIGNATURE]: 'pr2-live-world', [LiveInfoKey.SCENE]: 'pr2-live', [LiveInfoKey.CAPABILITIES]: [] }
        : { [LiveStateKey.SEQUENCE_NUMBER]: 1, joints: { shoulder: 0.5 } };
      return { ok: true, json: async () => answer };
    }
    const route = url.split('/api/plugins/laboratory/')[1];
    const answers = {
      [LaboratoryRoute.LABORATORIES]: { laboratories: [{ name: 'aicor_medical_lab', title: 'Small lab' }], physicsAvailable: false },
      [LaboratoryRoute.DEVICES]: { devices: [] },
      [LaboratoryRoute.TRANSFER_STATE]: { state: transfer, scene: 'aicor_medical_lab_pr2_transfer', liveUrl: transfer === TaskRunState.RUNNING ? '/api/plugins/laboratory/transfer/live/' : null },
      [LaboratoryRoute.PREVIEW]: { scene: PREVIEW },
      [LaboratoryRoute.INSTALL]: { scene: 'aicor_medical_lab' },
      [LaboratoryRoute.START]: { scene: 'aicor_medical_lab_contact_physics' },
    };
    const failed = route === LaboratoryRoute.PREVIEW && !previewAvailable;
    return { ok: !failed, status: failed ? 503 : 200, json: async () => failed ? { error: 'The PR2 preview needs CRAM.' } : answers[route] };
  };
  const api = new ViewerApi(fetch, viewerRootOf(PAGE));
  const loaded = (name) => ({
    name, description: {}, frames: { framesPerSecond: 30, frameCount: name.startsWith('recorded') ? 91 : 1, segmentAt: () => -1 },
    missingFiles: () => [], dispose() {}, showFrame(frame) { frames.push(frame); }, showState(snapshot) { states.push(snapshot); },
  });
  const page = new LaboratoryPage(root, {
    api, location, history, fetch, timer: new FakeTimer(), timers,
    createView: () => view,
    createLoader: () => ({ async load(name) { scenes.push(name); return loaded(name); } }),
  });
  return { page, root, document, requested, scenes, states, frames, intervals, location, view };
}

test('the page resolves its API under a deployment prefix', () => {
  assert.equal(viewerRootOf(PAGE), 'http://viewer/demo/');
});

test('entering the dedicated page prepares and displays the PR2 with the small lab', async () => {
  const { page, root, requested, scenes, document } = environment();
  await page.start();
  assert.deepEqual(scenes, [PREVIEW]);
  assert.ok(requested.some(({ url, options }) => url === 'http://viewer/demo/api/plugins/laboratory/preview' && options.method === 'POST'));
  assert.equal(document.documentElement.dataset.viewerState, 'ready');
  assert.equal(root.findAll((element) => element.tagName === 'IFRAME').length, 0);
  assert.equal(root.findAll((element) => element.getAttribute('role') === 'tablist').length, 0);
  assert.ok(root.innerText.includes(Text.PHYSICS_SETUP));
  page.dispose();
});

test('missing CRAM leaves an operable compact lab with actionable PR2 setup help', async () => {
  const { page, root, scenes, requested } = environment({ previewAvailable: false });
  await page.start();
  assert.deepEqual(scenes, ['aicor_medical_lab']);
  assert.ok(root.innerText.includes('The PR2 preview needs CRAM.'));
  assert.ok(root.innerText.includes('scripts/install_stack.py'));
  const install = requested.find(({ url }) => url.endsWith('/install'));
  assert.deepEqual(JSON.parse(install.options.body), { laboratory: 'aicor_medical_lab' });
  page.dispose();
});

test('a running PR2 follows live poses through the prefixed local proxy, then opens its saved replay', async () => {
  const { page, root, scenes, states, intervals, requested } = environment({ transfer: TaskRunState.RUNNING });
  await page.start();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(scenes, [PREVIEW, 'pr2-live']);
  assert.ok(requested.some(({ url }) => url === 'http://viewer/demo/api/plugins/laboratory/transfer/live/info'));
  await intervals.get(100)();
  assert.equal(states.length, 1);
  assert.ok(root.innerText.includes('Following the local PR2'));
  page.followTransfer({ [TaskRunKey.STATE]: TaskRunState.RECORDED, [TaskRunKey.SCENE]: 'recorded-pr2' });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(scenes.at(-1), 'recorded-pr2');
  assert.equal(intervals.size, 0);
  page.dispose();
});

test('opening another lab scene stays on the dedicated page and releases its view on exit', async () => {
  const { page, scenes, location, view } = environment();
  await page.start();
  await page.show('aicor_medical_lab_contact_physics');
  assert.deepEqual(scenes, [PREVIEW, 'aicor_medical_lab_contact_physics']);
  assert.equal(new URL(location.href).pathname, '/demo/plugins/laboratory/laboratory.html');
  assert.equal(new URL(location.href).searchParams.get('scene'), 'aicor_medical_lab_contact_physics');
  page.dispose();
  assert.equal(view.disposed, true);
});

test('the saved PR2 recording plays and seeks through the dedicated page timeline', async () => {
  const { page, root, frames, view } = environment();
  await page.start();
  await page.show('recorded-pr2');
  const play = root.findAll((element) => element.tagName === 'BUTTON' && element.textContent === '▶ Play')[0];
  assert.equal(play.disabled, false);
  play.click();
  view.tick(0.5);
  assert.equal(frames.at(-1), 15);
  const slider = root.findAll((element) => element.getAttribute('aria-label') === 'Frame')[0];
  slider.value = '45';
  slider.dispatch('input');
  assert.equal(frames.at(-1), 45);
  page.dispose();
});
