import { test } from 'node:test';
import assert from 'node:assert/strict';

import { EventBus } from 'cramera-viewer/core/event-bus.js';
import { ViewerApi } from 'cramera-viewer/core/viewer-api.js';
import { PanelHost } from 'cramera-viewer/panels/panel-host.js';
import { QuerySlot } from 'cramera-viewer/panels/query-slot.js';
import {
  AnswerColumn,
  BundleFile,
  GraphViewKey,
  GraphViewName,
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
  RecordedAnswerKey,
  RecordedAnswersKey,
  ReplayWindowKey,
  ScopeDescriptionKey,
  Serving,
  VerbalizationKey,
  ViewerEvent,
  ViewerInfoKey,
} from 'cramera-viewer/protocol.js';
import { FakeDocument } from 'cramera-testing/fake-document.mjs';

import { AnswerView } from '../../src/cramera_questions/web/answer-view.js';
import { VIEW_TITLES } from '../../src/cramera_questions/web/graph-panel.js';
import { graphPanelOf, register } from '../../src/cramera_questions/web/index.js';
import { QuestionsClient } from '../../src/cramera_questions/web/questions-client.js';
import { Hint, QuestionsPanel, Status } from '../../src/cramera_questions/web/questions-panel.js';
import { AnswerSources, NotRecorded, RecordedAnswersClient, SceneSource } from '../../src/cramera_questions/web/recorded-answers.js';

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

/**
 * @param {Object} client A client.
 * @returns {SceneSource} The client as the source of a scene, with its catalog.
 */
function sourceOf(client, recordedAt = null) {
  return new SceneSource(client, CATALOG, recordedAt);
}

test('a scene offers its ready-made questions, and one runs, reads back, highlights and replays', async () => {
  const bus = new EventBus();
  const highlights = published(bus, ViewerEvent.ENTITY_HIGHLIGHTED);
  const frames = published(bus, ViewerEvent.FRAME_REQUESTED);
  const playback = published(bus, ViewerEvent.PLAYBACK_REQUESTED);
  const { client, calls } = fakeClient();
  const panel = new QuestionsPanel(new FakeDocument(), bus);
  panel.showScene('cell', sourceOf({ ...client, readOnly: false }));
  assert.equal(panel.status.textContent, Status.LIVE);
  const presets = panel.element.findAll((element) => element.className === 'preset');
  assert.deepEqual(presets.map((button) => button.textContent), ['which robot is this?']);
  presets[0].dispatch('click');
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(calls.at(-1), ['query', 'cell', 'the(entity(robot))', QueryScope.EPISODIC_MEMORY]);
  assert.deepEqual(highlights, [[], ANSWER[QueryAnswerKey.HIGHLIGHT]]);
  const [reading] = panel.element.findAll((element) => element.className === 'question');
  assert.equal(reading.textContent, ANSWER[QueryAnswerKey.VERBALIZATION][VerbalizationKey.TEXT]);
  const table = panel.element.findAll((element) => element.tagName === 'TABLE')[0];
  table.children[1].children[3].children[0].dispatch('click');
  assert.deepEqual(frames, [12]);
  assert.deepEqual(playback, [true]);
});

test('before anything is asked the panel shows its hints', () => {
  const panel = new QuestionsPanel(new FakeDocument(), new EventBus());
  assert.match(panel.element.innerText, new RegExp(Hint.QUESTION));
  assert.equal(panel.status.textContent, Status.LOADING);
});

test('a question runs the preset it matches, or says why none does', async () => {
  const matched = fakeClient();
  const panel = new QuestionsPanel(new FakeDocument(), new EventBus());
  panel.showScene('cell', sourceOf(matched.client));
  await panel.ask('Which robot is this one?');
  assert.deepEqual(matched.calls.slice(-2).map((call) => call[0]), ['question', 'query']);
  const unmatched = fakeClient({ [QuestionMatchKey.MATCHED]: false, [QuestionMatchKey.REPLY]: 'I do not know that one.' });
  const other = new QuestionsPanel(new FakeDocument(), new EventBus());
  other.showScene('cell', sourceOf(unmatched.client));
  await other.ask('What is the weather?');
  assert.match(other.element.innerText, /I do not know that one\./);
  assert.equal(unmatched.calls.some((call) => call[0] === 'query'), false);
});

test('nothing is asked before a scene is shown or for empty text', async () => {
  const { client, calls } = fakeClient();
  const panel = new QuestionsPanel(new FakeDocument(), new EventBus());
  await panel.ask('which robot?');
  await panel.run('code()', QueryScope.EPISODIC_MEMORY);
  panel.showScene('cell', sourceOf(client));
  await panel.ask('   ');
  assert.deepEqual(calls, []);
});

test('a scene whose questions cannot be listed says why', () => {
  const panel = new QuestionsPanel(new FakeDocument(), new EventBus());
  const failed = { [PresetCatalogKey.OK]: false, [PresetCatalogKey.ERROR]: 'krrood is missing' };
  panel.showScene('cell', new SceneSource(fakeClient().client, failed, null));
  assert.equal(panel.status.textContent, Status.UNAVAILABLE);
  assert.match(panel.element.innerText, /krrood is missing/);
});

test('recorded answers disable the query boxes and say why', () => {
  const panel = new QuestionsPanel(new FakeDocument(), new EventBus());
  panel.showScene('cell', sourceOf({ ...fakeClient().client, readOnly: true }, '2026-10-23T10:00:00Z'));
  const [code] = panel.element.findAll((element) => element.tagName === 'TEXTAREA');
  const [question] = panel.element.findAll((element) => element.tagName === 'INPUT');
  assert.equal(code.disabled, true);
  assert.equal(question.disabled, true);
  assert.equal(code.placeholder, Hint.QUERY_DISABLED);
  const [note] = panel.element.findAll((element) => element.className === 'recorded-note');
  assert.equal(note.hidden, false);
  assert.match(note.textContent, /2026-10-23T10:00:00Z/);
  assert.match(panel.status.textContent, /recorded answers/);
});

// %% recorded answers

const RECORDED = {
  [RecordedAnswersKey.FORMAT_VERSION]: '1.0',
  [RecordedAnswersKey.SCENE]: 'cell',
  [RecordedAnswersKey.RECORDED_AT]: '2026-10-23T10:00:00Z',
  [RecordedAnswersKey.PRESETS]: CATALOG,
  [RecordedAnswersKey.ANSWERS]: [
    { [RecordedAnswerKey.CODE]: 'the(entity(robot))', [RecordedAnswerKey.SCOPE]: QueryScope.EPISODIC_MEMORY, [RecordedAnswerKey.ANSWER]: ANSWER },
  ],
  [RecordedAnswersKey.GRAPHS]: [{ [GraphViewKey.VIEW]: GraphViewName.PLAN, [GraphViewKey.NODES]: [] }],
};

/**
 * @param {Object<string, Object>} files The answer of each path below the base.
 * @param {Array<string>} requested Collects the requested URLs.
 * @returns {function(string): Promise<Object>} A fetch answering only those files.
 */
function filesFetch(files, requested = []) {
  return async (url) => {
    requested.push(url);
    const path = new URL(url).pathname.replace('/cramera/', '');
    const found = files[path];
    return found
      ? { ok: true, status: 200, headers: new Map(), json: async () => found }
      : { ok: false, status: 404, statusText: 'Not Found', headers: new Map(), json: async () => ({}) };
  };
}

const RECORDED_PATH = `scenes/cell/${BundleFile.RECORDED_ANSWERS}`;

test('recorded answers answer the recorded queries and views, and nothing else', async () => {
  const requested = [];
  const client = new RecordedAnswersClient(new ViewerApi(filesFetch({ [RECORDED_PATH]: RECORDED }, requested), BASE));
  assert.equal(client.readOnly, true);
  assert.deepEqual(await client.presets('cell'), CATALOG);
  assert.deepEqual(await client.query('cell', 'the(entity(robot))', QueryScope.EPISODIC_MEMORY), ANSWER);
  assert.deepEqual(await client.query('cell', 'other()', QueryScope.EPISODIC_MEMORY), { [QueryAnswerKey.OK]: false, [QueryAnswerKey.ERROR]: NotRecorded.QUERY });
  assert.equal((await client.graph('cell', GraphViewName.PLAN))[GraphViewKey.VIEW], GraphViewName.PLAN);
  assert.equal((await client.graph('cell', GraphViewName.KINEMATICS))[GraphViewKey.ERROR], NotRecorded.VIEW);
  assert.equal((await client.question('cell', 'which robot?'))[QuestionMatchKey.MATCHED], false);
  assert.equal(requested.length, 1);
});

test('a scene without recorded answers says so', async () => {
  const client = new RecordedAnswersClient(new ViewerApi(filesFetch({}), BASE));
  assert.equal((await client.presets('cell'))[PresetCatalogKey.ERROR], NotRecorded.SCENE);
  assert.equal((await client.graph('cell', GraphViewName.PLAN))[GraphViewKey.ERROR], NotRecorded.SCENE);
});

test('the routes answer where they list the scene\'s questions, else the recorded answers', async () => {
  const api = new ViewerApi(filesFetch({ [RECORDED_PATH]: RECORDED }), BASE);
  const recorded = new RecordedAnswersClient(api);
  const answering = { presets: async () => CATALOG, readOnly: false };
  const served = await new AnswerSources(answering, recorded).forScene('cell');
  assert.equal(served.client, answering);
  assert.equal(served.recordedAt, null);
  const missing = { presets: async () => ({ [PresetCatalogKey.OK]: false, [PresetCatalogKey.ERROR]: 'krrood is missing' }) };
  const fallback = await new AnswerSources(missing, recorded).forScene('cell');
  assert.equal(fallback.client, recorded);
  assert.equal(fallback.recordedAt, RECORDED[RecordedAnswersKey.RECORDED_AT]);
  const unreachable = { presets: async () => { throw new Error('404'); } };
  assert.equal((await new AnswerSources(unreachable, recorded).forScene('cell')).client, recorded);
  const staticSite = await new AnswerSources(null, recorded).forScene('cell');
  assert.equal(staticSite.client, recorded);
  const nothing = await new AnswerSources(missing, new RecordedAnswersClient(new ViewerApi(filesFetch({}), BASE))).forScene('cell');
  assert.equal(nothing.client, missing);
  assert.equal(nothing.catalog[PresetCatalogKey.ERROR], 'krrood is missing');
  const nothingStatic = await new AnswerSources(null, new RecordedAnswersClient(new ViewerApi(filesFetch({}), BASE))).forScene('cell');
  assert.equal(nothingStatic.catalog[PresetCatalogKey.ERROR], NotRecorded.SCENE);
});

// %% registration

/**
 * @param {Object} info The viewer's information.
 * @param {function} fetch Answers the requests.
 * @returns {{context: Object, document: FakeDocument}} What register receives.
 */
function contextOf(info, fetch) {
  const document = new FakeDocument();
  const bus = new EventBus();
  const panels = new PanelHost(document.createElement('aside'));
  const query = new QuerySlot(document.createElement('section'));
  const view = { renderer: { domElement: { ownerDocument: document } } };
  return { document, context: { bus, panels, query, api: new ViewerApi(fetch, BASE), view, info } };
}

test('registering fills the query slot, adds a tab per graph view and follows the shown scene', async () => {
  const requested = [];
  const answers = { [`api/plugins/${PluginName.QUESTIONS}/${QuestionsRoute.PRESETS}`]: CATALOG, [`api/plugins/${PluginName.QUESTIONS}/${QuestionsRoute.GRAPH}`]: { [GraphViewKey.NODES]: [] } };
  const { document, context } = contextOf({ [ViewerInfoKey.SERVING]: Serving.SERVER }, filesFetch(answers, requested));
  const panel = register(context);
  assert.equal(context.query.occupant, PluginName.QUESTIONS);
  assert.deepEqual(context.panels.identifiers(), Object.keys(VIEW_TITLES).map(graphPanelOf));
  assert.equal(document.head.children.length, 1);
  context.bus.publish(ViewerEvent.SCENE_LOADED, { name: 'cell' });
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(panel.element.findAll((element) => element.className === 'preset').length, 1);
  assert.ok(requested.every((url) => url.includes('/api/plugins/')));
});

test('on a static site registering reads the recorded answers and asks no route', async () => {
  const requested = [];
  const { context } = contextOf({ [ViewerInfoKey.SERVING]: Serving.STATIC }, filesFetch({ [RECORDED_PATH]: RECORDED }, requested));
  const panel = register(context);
  context.bus.publish(ViewerEvent.SCENE_LOADED, { name: 'cell' });
  for (let turn = 0; turn < 4; turn += 1) await new Promise((resolve) => setTimeout(resolve, 0));
  assert.ok(requested.length > 0);
  assert.ok(requested.every((url) => url.endsWith(RECORDED_PATH)));
  assert.match(panel.status.textContent, /recorded answers/);
});
