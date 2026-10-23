import { test } from 'node:test';
import assert from 'node:assert/strict';

import { EventBus } from 'cramera-viewer/core/event-bus.js';
import { ViewerApi } from 'cramera-viewer/core/viewer-api.js';
import {
  GraphDetailKey,
  GraphEdgeKey,
  GraphEdgeKind,
  GraphLayout,
  GraphNodeKey,
  GraphViewKey,
  GraphViewName,
  LegendEntryKey,
  QuestionsParameter,
  QuestionsRoute,
  ViewerEvent,
} from 'cramera-viewer/protocol.js';
import { FakeDocument } from 'cramera-testing/fake-document.mjs';

import { placeNodes } from '../../src/cramera_questions/web/graph-layout.js';
import { GraphPanel, VIEW_TITLES } from '../../src/cramera_questions/web/graph-panel.js';
import { GraphView, PALETTE_SIZE } from '../../src/cramera_questions/web/graph-view.js';
import { QuestionsClient } from '../../src/cramera_questions/web/questions-client.js';

const BASE = 'https://sunava.github.io/cramera/';

function node(identifier, group) {
  return { [GraphNodeKey.IDENTIFIER]: identifier, [GraphNodeKey.LABEL]: identifier, [GraphNodeKey.GROUP]: group };
}

function edge(source, destination, kind = GraphEdgeKind.PROPERTY) {
  return { [GraphEdgeKey.SOURCE]: source, [GraphEdgeKey.DESTINATION]: destination, [GraphEdgeKey.KIND]: kind };
}

function treeView(layout) {
  return {
    [GraphViewKey.VIEW]: GraphViewName.KINEMATICS,
    [GraphViewKey.LAYOUT]: layout,
    [GraphViewKey.NODES]: [node('base', 'link'), node('left', 'link'), node('right', 'joint')],
    [GraphViewKey.EDGES]: [edge('base', 'left'), edge('base', 'right', GraphEdgeKind.TYPE)],
    [GraphViewKey.LEGEND]: [
      { [LegendEntryKey.GROUP]: 'link', [LegendEntryKey.LABEL]: 'Link' },
      { [LegendEntryKey.GROUP]: 'joint', [LegendEntryKey.LABEL]: 'Joint' },
    ],
    [GraphViewKey.DETAILS]: { base: { [GraphDetailKey.LABEL]: 'base', [GraphDetailKey.GROUP]: 'link', [GraphDetailKey.LINES]: ['mass: 1'] } },
  };
}

function fakeFetch(answers, requested) {
  return async (url, options = {}) => {
    requested.push(String(url));
    if (options.signal?.aborted) throw new DOMException('aborted', 'AbortError');
    const answer = answers.shift();
    return { ok: true, status: 200, json: async () => answer };
  };
}

// %% layout

test('a hierarchy puts children one layer below their parent, centred under it', () => {
  const places = placeNodes(treeView(GraphLayout.HIERARCHY));
  const [base, left, right] = ['base', 'left', 'right'].map((name) => places.get(name));
  assert.ok(left.y > base.y);
  assert.equal(left.y, right.y);
  assert.notEqual(left.x, right.x);
  assert.equal(base.x, (left.x + right.x) / 2);
});

test('a left-to-right hierarchy swaps the axes', () => {
  const down = placeNodes(treeView(GraphLayout.HIERARCHY));
  const across = placeNodes(treeView(GraphLayout.HIERARCHY_LEFT_RIGHT));
  for (const [name, place] of down) assert.deepEqual({ ...across.get(name) }, { x: place.y, y: place.x });
});

test('a free layout places every node, deterministically and apart', () => {
  const view = treeView(GraphLayout.FREE);
  const first = placeNodes(view);
  assert.deepEqual(placeNodes(view), first);
  const places = [...first.values()];
  assert.equal(places.length, 3);
  assert.ok(places.every((place) => Number.isFinite(place.x) && Number.isFinite(place.y)));
  assert.equal(new Set(places.map((place) => `${place.x},${place.y}`)).size, 3);
});

test('a view without nodes places nothing', () => {
  assert.equal(placeNodes({}).size, 0);
});

// %% view

test('the view draws edges, nodes coloured by legend order, and the legend', () => {
  const document = new FakeDocument();
  const graph = new GraphView(document, () => {});
  graph.show(treeView(GraphLayout.HIERARCHY));
  const lines = graph.element.findAll((element) => element.tagName === 'line');
  assert.equal(lines.length, 2);
  assert.ok(lines[1].getAttribute('class').includes(GraphEdgeKind.TYPE));
  const marks = graph.element.findAll((element) => element.getAttribute('class')?.startsWith('graph-node'));
  assert.deepEqual(marks.map((mark) => mark.getAttribute('class')), ['graph-node series-0', 'graph-node series-0', 'graph-node series-1']);
  const legend = graph.element.findAll((element) => element.tagName === 'LI');
  assert.deepEqual(legend.map((item) => item.textContent), ['Link', 'Joint']);
  assert.ok(PALETTE_SIZE >= legend.length);
});

test('clicking a node shows its details and reports its identity', () => {
  const document = new FakeDocument();
  const chosen = [];
  const graph = new GraphView(document, (identity) => chosen.push(identity));
  graph.show(treeView(GraphLayout.HIERARCHY));
  const [base] = graph.element.findAll((element) => element.getAttribute('class')?.startsWith('graph-node'));
  base.dispatch('click');
  assert.deepEqual(chosen, ['base']);
  assert.match(graph.element.innerText, /mass: 1/);
});

// %% controls

test('the buttons zoom around the middle, fit the graph again and fill the window', () => {
  const graph = new GraphView(new FakeDocument(), () => {});
  graph.show(treeView(GraphLayout.HIERARCHY));
  const drawing = graph.element.children[0];
  const fitted = drawing.getAttribute('viewBox').split(' ').map(Number);
  const [fullscreen, zoomIn, zoomOut, fit] = graph.element.children[1].children;
  zoomIn.dispatch('click');
  const zoomed = drawing.getAttribute('viewBox').split(' ').map(Number);
  assert.ok(zoomed[2] < fitted[2]);
  assert.ok(Math.abs(zoomed[0] + zoomed[2] / 2 - (fitted[0] + fitted[2] / 2)) < 1e-9);
  zoomOut.dispatch('click');
  zoomOut.dispatch('click');
  assert.ok(Number(drawing.getAttribute('viewBox').split(' ')[2]) > fitted[2]);
  fit.dispatch('click');
  assert.deepEqual(drawing.getAttribute('viewBox').split(' ').map(Number), fitted);
  fullscreen.dispatch('click');
  assert.equal(graph.element.classList.contains('graph-fullscreen'), true);
});

// %% panel

test('a tab draws its own view of the shown scene from the scene\'s client', async () => {
  const document = new FakeDocument();
  const requested = [];
  const api = new ViewerApi(fakeFetch([treeView(GraphLayout.HIERARCHY)], requested), BASE);
  const bus = new EventBus();
  const highlighted = [];
  bus.subscribe(ViewerEvent.ENTITY_HIGHLIGHTED, (identities) => highlighted.push(identities));
  const panel = new GraphPanel(document, GraphViewName.KINEMATICS, bus);
  assert.deepEqual(Object.keys(VIEW_TITLES), [GraphViewName.KNOWLEDGE, GraphViewName.PLAN, GraphViewName.STATECHART, GraphViewName.KINEMATICS]);
  await panel.showScene('pr2-kitchen', new QuestionsClient(api));
  const url = new URL(requested[0]);
  assert.ok(url.pathname.endsWith(QuestionsRoute.GRAPH));
  assert.equal(url.searchParams.get(QuestionsParameter.SCENE), 'pr2-kitchen');
  assert.equal(url.searchParams.get(QuestionsParameter.VIEW), GraphViewName.KINEMATICS);
  const [base] = panel.element.findAll((element) => element.getAttribute('class')?.startsWith('graph-node'));
  base.dispatch('click');
  assert.deepEqual(highlighted, [['base']]);
});

test('a tab says why its view cannot be drawn, or that it is empty', async () => {
  const document = new FakeDocument();
  const answers = [
    { [GraphViewKey.OK]: false, [GraphViewKey.ERROR]: 'krrood is not installed' },
    { [GraphViewKey.OK]: true, [GraphViewKey.NODES]: [], [GraphViewKey.EMPTY]: 'This scene has no plan.' },
  ];
  const client = new QuestionsClient(new ViewerApi(fakeFetch(answers, []), BASE));
  const panel = new GraphPanel(document, GraphViewName.PLAN, new EventBus());
  await panel.showScene('pr2-kitchen', client);
  assert.match(panel.element.innerText, /krrood is not installed/);
  await panel.showScene('pr2-kitchen', client);
  assert.match(panel.element.innerText, /This scene has no plan\./);
  assert.equal(panel.element.findAll((element) => element.tagName === 'circle').length, 0);
});

test('a scene shown while another loads replaces it', async () => {
  let release;
  const slow = { graph: () => new Promise((resolve) => { release = resolve; }) };
  const fast = { graph: async () => ({ [GraphViewKey.NODES]: [], [GraphViewKey.EMPTY]: 'second' }) };
  const panel = new GraphPanel(new FakeDocument(), GraphViewName.PLAN, new EventBus());
  const first = panel.showScene('first', slow);
  await panel.showScene('second', fast);
  release({ [GraphViewKey.NODES]: [], [GraphViewKey.EMPTY]: 'first' });
  await first;
  assert.match(panel.element.innerText, /second/);
});
