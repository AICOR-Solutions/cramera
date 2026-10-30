import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SceneRunsName, SceneRunState, ViewerEvent } from 'cramera-viewer/protocol.js';
import { EventBus } from 'cramera-viewer/core/event-bus.js';
import { POLL_INTERVAL, PANEL_TITLE, register, replayAddress, stateText } from '../../src/cramera_scene_runs/web/index.js';
import { FakeDocument } from 'cramera-testing/fake-document.mjs';

const PAGE = 'https://cramera.example.org/phone/?live=http%3A%2F%2F127.0.0.1%3A8765&panel=scene-runs';

const RUNS = [
  { identifier: 'pr2_transfer', label: 'PR2 vessel transfer', scene: 'aicor_medical_lab_pr2' },
  { identifier: 'fr3_plates', label: 'FR3 plate cycle' },
];

const status = (state, extra = {}) => ({ identifier: 'pr2_transfer', state, recording: 'pr2_transfer_20261028_120000', log: '', ...extra });

/**
 * A stand-in for the viewer's routes: answers from a list and records every request.
 */
class FakeApi {
  constructor(answers) {
    this.answers = answers;
    this.requests = [];
  }

  url(route) {
    return new URL(route.replace(/^\//, ''), 'https://cramera.example.org/phone/').href;
  }

  async json(url) {
    return this.#answer('GET', url);
  }

  async postJson(url, body) {
    return this.#answer('POST', url, body);
  }

  async #answer(method, url, body) {
    this.requests.push({ method, url, body });
    const answer = this.answers.shift();
    if (answer instanceof Error) throw answer;
    return answer;
  }
}

function registered(answers) {
  const api = new FakeApi(answers);
  const bus = new EventBus();
  const live = [];
  bus.subscribe(ViewerEvent.LIVE_REQUESTED, (address) => live.push(address));
  const added = [];
  const intervals = [];
  const assigned = [];
  const location = { href: PAGE, assign: (href) => assigned.push(href) };
  const panel = register(
    { api, bus, panels: { add: (side) => added.push(side) } },
    new FakeDocument(),
    { setInterval: (callback, milliseconds) => intervals.push({ callback, milliseconds }) },
    location,
  );
  return { api, panel, live, added, intervals, assigned };
}

const settled = () => new Promise((resolve) => setTimeout(resolve, 0));

// %% words

test('the state is told in a sentence', () => {
  assert.equal(stateText(null, RUNS), 'No run started yet.');
  assert.equal(stateText(null, []), 'This viewer offers no runs.');
  assert.match(stateText(status(SceneRunState.RUNNING), RUNS), /^PR2 vessel transfer runs; its queries wait for Next/);
  assert.equal(stateText(status(SceneRunState.RECORDED), RUNS), 'PR2 vessel transfer was recorded as pr2_transfer_20261028_120000.');
  assert.equal(stateText(status(SceneRunState.STOPPED), RUNS), 'PR2 vessel transfer was stopped.');
  assert.equal(stateText(status(SceneRunState.FAILED, { identifier: 'gone' }), RUNS), 'gone failed:');
});

test('a replay shows the recording instead of the live run', () => {
  const url = replayAddress(PAGE, 'pr2_transfer_20261028_120000');
  assert.equal(url.searchParams.get('scene'), 'pr2_transfer_20261028_120000');
  assert.equal(url.searchParams.get('live'), null);
  assert.equal(url.searchParams.get('panel'), 'scene-runs');
});

// %% panel

test('the panel lists the offered runs and reads their state regularly', async () => {
  const { api, added, intervals, panel } = registered([{ runs: RUNS }]);
  await settled();
  assert.equal(added[0].identifier, SceneRunsName.PLUGIN);
  assert.equal(added[0].title, PANEL_TITLE);
  assert.equal(api.requests[0].url, 'https://cramera.example.org/phone/api/plugins/scene-runs/state');
  assert.equal(intervals[0].milliseconds, POLL_INTERVAL);
  const [, runs, state] = panel.element.children;
  assert.equal(runs.children.length, 2);
  assert.equal(runs.children[0].children[0].textContent, 'PR2 vessel transfer');
  assert.equal(runs.children[0].children.length, 3, 'Start and Replay of the recorded run');
  assert.equal(runs.children[1].children.length, 2, 'Start only');
  assert.equal(state.textContent, 'No run started yet.');
});

test('starting a run follows it live and offers to stop it', async () => {
  const { api, panel, live } = registered([{ runs: RUNS }, { runs: RUNS, current: status(SceneRunState.RUNNING) }, { runs: RUNS, current: status(SceneRunState.STOPPED) }]);
  await settled();
  const [, runs, , controls] = panel.element.children;
  runs.children[0].children[1].dispatch('click');
  await settled();
  assert.deepEqual(api.requests[1], { method: 'POST', url: 'https://cramera.example.org/phone/api/plugins/scene-runs/start/pr2_transfer', body: {} });
  assert.deepEqual(live, [null]);
  assert.equal(runs.children[1].children[1].disabled, true, 'no second run while one runs');
  controls.children[0].dispatch('click');
  await settled();
  assert.equal(api.requests[2].url, 'https://cramera.example.org/phone/api/plugins/scene-runs/stop');
  assert.equal(controls.children.length, 0);
});

test('a recorded run is replayed, and an offered recording too', async () => {
  const { panel, assigned } = registered([{ runs: RUNS, current: status(SceneRunState.RECORDED) }]);
  await settled();
  const [, runs, , controls] = panel.element.children;
  controls.children[0].dispatch('click');
  runs.children[0].children[2].dispatch('click');
  assert.equal(new URL(assigned[0]).searchParams.get('scene'), 'pr2_transfer_20261028_120000');
  assert.equal(new URL(assigned[1]).searchParams.get('scene'), 'aicor_medical_lab_pr2');
});

test('a failed run shows the end of its output', async () => {
  const { panel } = registered([{ runs: RUNS, current: status(SceneRunState.FAILED, { log: 'the robot could not reach the vessel' }) }]);
  await settled();
  const [, , state, controls] = panel.element.children;
  assert.equal(state.textContent, 'PR2 vessel transfer failed:');
  assert.equal(controls.children[0].textContent, 'the robot could not reach the vessel');
});

test('a refused start says why and follows nothing', async () => {
  const { panel, live } = registered([{ runs: RUNS }, new Error('FR3 plate cycle runs; stop it first, one run runs at a time.')]);
  await settled();
  const [, runs, , , notice] = panel.element.children;
  runs.children[0].children[1].dispatch('click');
  await settled();
  assert.match(notice.textContent, /one run runs at a time/);
  assert.deepEqual(live, []);
});
