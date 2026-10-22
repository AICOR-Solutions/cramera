import { test } from 'node:test';
import assert from 'node:assert/strict';

import { EventBus } from 'cramera-viewer/core/event-bus.js';
import { ViewerApi } from 'cramera-viewer/core/viewer-api.js';
import { PanelHost } from 'cramera-viewer/panels/panel-host.js';
import {
  AnswerColumn,
  PluginName,
  PresetCatalogKey,
  PresetKey,
  QueryAnswerKey,
  QueryRequestKey,
  QueryScope,
  QuestionMatchKey,
  QuestionRequestKey,
  QuestionsParameter,
  QuestionsRoute,
  ReplayWindowKey,
  ScopeDescriptionKey,
  VerbalizationKey,
  ViewerEvent,
} from 'cramera-viewer/protocol.js';
import { FakeDocument } from 'cramera-testing/fake-document.mjs';

import { AnswerView } from '../../src/cramera_questions/web/answer-view.js';
import { register } from '../../src/cramera_questions/web/index.js';
import { QuestionsClient } from '../../src/cramera_questions/web/questions-client.js';
import { QuestionsPanel } from '../../src/cramera_questions/web/questions-panel.js';

const BASE = 'https://sunava.github.io/cramera/';

const CATALOG = {
  [PresetCatalogKey.OK]: true,
  [PresetCatalogKey.SCOPES]: [{ [ScopeDescriptionKey.NAME]: QueryScope.EPISODIC_MEMORY, [ScopeDescriptionKey.LABEL]: 'Episode' }],
  [PresetCatalogKey.PRESETS]: [
    { [PresetKey.TEXT]: 'which robot is this?', [PresetKey.CODE]: 'the(entity(robot))', [PresetKey.SCOPE]: QueryScope.EPISODIC_MEMORY },
    { [PresetKey.TEXT]: 'what is the robot doing now?', [PresetKey.CODE]: 'live()', [PresetKey.SCOPE]: QueryScope.CURRENT_STATE, [PresetKey.REQUIRES_LIVE]: true },
  ],
};

const ANSWER = {
  [QueryAnswerKey.OK]: true,
  [QueryAnswerKey.ROWS]: [{ x: 1, [AnswerColumn.TYPE]: 'Robot', [AnswerColumn.ENTITY]: 'pr2' }],
  [QueryAnswerKey.COUNT]: 1,
  [QueryAnswerKey.HIGHLIGHT]: ['base_link'],
  [QueryAnswerKey.REPLAY]: [{ [ReplayWindowKey.START]: 12, [ReplayWindowKey.END]: 40 }],
  [QueryAnswerKey.VERBALIZATION]: { [VerbalizationKey.TEXT]: 'the robot', [VerbalizationKey.HTML]: '<b>the robot</b>' },
};

/**
 * @returns {{client: Object, calls: Array}} A client answering from fixed documents.
 */
function fakeClient(match = { [QuestionMatchKey.MATCHED]: true, [QuestionMatchKey.PRESET]: CATALOG[PresetCatalogKey.PRESETS][0] }) {
  const calls = [];
  return {
    calls,
    client: {
      presets: async (scene) => { calls.push(['presets', scene]); return CATALOG; },
      query: async (scene, code, scope) => { calls.push(['query', scene, code, scope]); return ANSWER; },
      question: async (scene, text) => { calls.push(['question', scene, text]); return match; },
    },
  };
}

function published(bus, event) {
  const payloads = [];
  bus.subscribe(event, (payload) => payloads.push(payload));
  return payloads;
}

// %% client

test('the client calls the plugin routes below the page base', async () => {
  const requests = [];
  const fetch = async (url, init) => {
    requests.push({ url, init });
    return { ok: true, headers: new Map(), json: async () => ({}) };
  };
  const client = new QuestionsClient(new ViewerApi(fetch, BASE));
  await client.presets('pr2 warehouse');
  await client.query('cell', 'code()', QueryScope.EPISODIC_MEMORY);
  await client.question('cell', 'which robot?');
  const presets = new URL(requests[0].url);
  assert.equal(presets.pathname, `/cramera/api/plugins/${PluginName.QUESTIONS}/${QuestionsRoute.PRESETS}`);
  assert.equal(presets.searchParams.get(QuestionsParameter.SCENE), 'pr2 warehouse');
  assert.deepEqual(JSON.parse(requests[1].init.body), { [QueryRequestKey.SCENE]: 'cell', [QueryRequestKey.CODE]: 'code()', [QueryRequestKey.SCOPE]: QueryScope.EPISODIC_MEMORY });
  assert.deepEqual(JSON.parse(requests[2].init.body), { [QuestionRequestKey.SCENE]: 'cell', [QuestionRequestKey.TEXT]: 'which robot?' });
});

// %% answers

test('an answer shows its English reading as text, describing columns first, and replay buttons', () => {
  const replayed = [];
  const view = new AnswerView(new FakeDocument(), (window) => replayed.push(window));
  view.show(ANSWER);
  const [reading, count, table] = view.element.children;
  assert.equal(reading.textContent, 'the robot');
  assert.match(count.textContent, /^1 answer$/);
  const headings = table.children[0].children.map((cell) => cell.textContent);
  assert.deepEqual(headings, ['Entity', 'Type', 'x', '']);
  const button = table.children[1].children[3].children[0];
  button.dispatch('click');
  assert.deepEqual(replayed, [ANSWER[QueryAnswerKey.REPLAY][0]]);
});

test('a failed answer shows its reason', () => {
  const view = new AnswerView(new FakeDocument(), () => {});
  view.show({ [QueryAnswerKey.OK]: false, [QueryAnswerKey.ERROR]: 'NameError: robot' });
  assert.equal(view.element.children[0].className, 'error');
  assert.equal(view.element.children[0].textContent, 'NameError: robot');
});

// %% panel

test('a scene offers its recorded questions, and one runs, highlights and replays', async () => {
  const bus = new EventBus();
  const highlights = published(bus, ViewerEvent.ENTITY_HIGHLIGHTED);
  const frames = published(bus, ViewerEvent.FRAME_REQUESTED);
  const playback = published(bus, ViewerEvent.PLAYBACK_REQUESTED);
  const { client, calls } = fakeClient();
  const panel = new QuestionsPanel(new FakeDocument(), client, bus);
  await panel.showScene('cell');
  const presets = panel.element.children[0].children;
  assert.deepEqual(presets.map((button) => button.textContent), ['which robot is this?']);
  presets[0].dispatch('click');
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(calls.at(-1), ['query', 'cell', 'the(entity(robot))', QueryScope.EPISODIC_MEMORY]);
  assert.deepEqual(highlights, [[], ANSWER[QueryAnswerKey.HIGHLIGHT]]);
  const table = panel.element.findAll((element) => element.tagName === 'TABLE')[0];
  table.children[1].children[3].children[0].dispatch('click');
  assert.deepEqual(frames, [12]);
  assert.deepEqual(playback, [true]);
});

test('a question runs the preset it matches, or says why none does', async () => {
  const matched = fakeClient();
  const panel = new QuestionsPanel(new FakeDocument(), matched.client, new EventBus());
  await panel.showScene('cell');
  await panel.ask('Which robot is this one?');
  assert.deepEqual(matched.calls.slice(-2).map((call) => call[0]), ['question', 'query']);
  const unmatched = fakeClient({ [QuestionMatchKey.MATCHED]: false, [QuestionMatchKey.REPLY]: 'I do not know that one.' });
  const other = new QuestionsPanel(new FakeDocument(), unmatched.client, new EventBus());
  await other.showScene('cell');
  await other.ask('What is the weather?');
  assert.match(other.element.innerText, /I do not know that one\./);
  assert.equal(unmatched.calls.some((call) => call[0] === 'query'), false);
});

test('nothing is asked before a scene is shown or for empty text', async () => {
  const { client, calls } = fakeClient();
  const panel = new QuestionsPanel(new FakeDocument(), client, new EventBus());
  await panel.ask('which robot?');
  await panel.run('code()', QueryScope.EPISODIC_MEMORY);
  await panel.showScene('cell');
  await panel.ask('   ');
  assert.deepEqual(calls.map((call) => call[0]), ['presets']);
});

// %% registration

test('registering adds the Questions panel and follows the shown scene', async () => {
  const document = new FakeDocument();
  const bus = new EventBus();
  const panels = new PanelHost(document.createElement('aside'));
  const { client } = fakeClient();
  const fetch = async () => ({ ok: true, headers: new Map(), json: async () => CATALOG });
  const panel = register({ bus, panels, api: new ViewerApi(fetch, BASE), view: { renderer: { domElement: { ownerDocument: document } } } });
  assert.deepEqual(panels.identifiers(), [PluginName.QUESTIONS, `${PluginName.QUESTIONS}-graph`]);
  assert.equal(document.head.children.length, 1);
  bus.publish(ViewerEvent.SCENE_LOADED, { name: 'cell' });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(panel.element.children[0].children.length, 1);
  assert.ok(client);
});
