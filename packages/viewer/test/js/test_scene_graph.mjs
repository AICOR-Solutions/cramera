import { test } from 'node:test';
import assert from 'node:assert/strict';

import { EventBus } from '../../src/cramera/web/core/event-bus.js';
import { SceneGraphPanel, UNFOLDED_DEPTH } from '../../src/cramera/web/panels/scene-graph-panel.js';
import { SelectionKey, SelectionKind, ViewerEvent } from '../../src/cramera/web/protocol.js';
import { FixedNode, NodeKind, SceneGraph } from '../../src/cramera/web/scene/scene-graph.js';
import { FakeDocument } from './support/fake-document.mjs';

/**
 * A robot with an arm and its gripper on a table environment, one free object, and the
 * arm and gripper annotated.
 */
const FACTS = Object.freeze({
  name: 'cell',
  models: [
    {
      name: 'arm',
      robot: true,
      urdf: 'arm.urdf',
      links: [
        { name: 'base', parent: null, joint: null },
        { name: 'gripper', parent: 'upper', joint: { name: 'wrist', type: 'fixed', axis: [0, 0, 1], lower: 0, upper: 0 } },
        { name: 'upper', parent: 'base', joint: { name: 'shoulder', type: 'revolute', axis: [0, 1, 0], lower: -1.5, upper: 1.5 } },
      ],
    },
    { name: 'environment', robot: false, urdf: 'environment.urdf', links: [{ name: 'table', parent: null, joint: null }] },
  ],
  objects: [{ key: 'k-milk', name: 'milk' }],
  parts: [
    { name: 'left_arm', role: 'arm', side: 'left', links: ['base', 'upper'], attachedTo: null },
    { name: 'left_gripper', role: 'end_effector', side: 'left', links: ['gripper'], attachedTo: 'left_arm' },
  ],
});

const labels = (nodes) => nodes.map((node) => node.label);

// %% graph

test('models hold their links nested by the joints that connect them', () => {
  const graph = SceneGraph.of(FACTS);
  assert.deepEqual(labels(graph.children(null)), ['cell']);
  assert.deepEqual(labels(graph.children(FixedNode.WORLD)), ['arm', 'environment', 'Free objects', 'Robot parts']);
  assert.deepEqual(labels(graph.children('model:arm')), ['base']);
  assert.deepEqual(labels(graph.children('link:arm/base')), ['upper']);
  assert.deepEqual(labels(graph.children('link:arm/upper')), ['gripper']);
  const upper = graph.node('link:arm/upper');
  assert.deepEqual(upper.fields, [['Model', 'arm'], ['Joint', 'shoulder'], ['Joint type', 'revolute'], ['Axis', '(0, 1, 0)'], ['Range', '-1.5 … 1.5']]);
  assert.deepEqual(graph.node('link:arm/gripper').fields.map(([name]) => name), ['Model', 'Joint', 'Joint type']);
  assert.deepEqual(upper.keys, ['upper']);
});

test('a part annotation depends on its links and on the part it is attached to', () => {
  const graph = SceneGraph.of(FACTS);
  const gripper = graph.node('part:left_gripper');
  assert.equal(gripper.kind, NodeKind.PART);
  assert.deepEqual(gripper.references.map((reference) => [reference.field, reference.target]), [['link', 'link:arm/gripper'], ['attached to', 'part:left_arm']]);
  assert.deepEqual(gripper.keys, ['gripper']);
  assert.deepEqual(graph.referencedBy('part:left_arm').map((entry) => [entry.field, entry.source.label]), [['attached to', 'left_gripper']]);
  assert.deepEqual(graph.referencedBy('link:arm/upper').map((entry) => entry.source.label).sort(), ['gripper', 'left_arm']);
});

test('the graph counts its entities, filters them and finds what the 3D view selected', () => {
  const graph = SceneGraph.of(FACTS);
  assert.deepEqual([...graph.counts()], [[NodeKind.MODEL, 2], [NodeKind.LINK, 4], [NodeKind.OBJECT, 1], [NodeKind.PART, 2]]);
  assert.equal(graph.matching('  '), null);
  assert.deepEqual([...graph.matching('GRIP')].sort(), ['group:parts', 'link:arm/base', 'link:arm/gripper', 'link:arm/upper', 'model:arm', 'part:left_gripper', 'world']);
  assert.equal(graph.nodeOf(SelectionKind.LINK, 'upper', 'arm'), 'link:arm/upper');
  assert.equal(graph.nodeOf(SelectionKind.OBJECT, 'k-milk'), 'object:k-milk');
  assert.equal(graph.nodeOf(SelectionKind.OBJECT, 'gone'), null);
  assert.deepEqual(graph.ancestors('link:arm/gripper'), ['world', 'model:arm', 'link:arm/base', 'link:arm/upper']);
});

test('a scene without objects or parts has no groups for them', () => {
  const graph = SceneGraph.of({ name: 'bare', models: [], objects: [], parts: [] });
  assert.deepEqual(graph.children(FixedNode.WORLD), []);
});

// %% panel

function openPanel() {
  const bus = new EventBus();
  const highlighted = [];
  bus.subscribe(ViewerEvent.ENTITY_HIGHLIGHTED, (keys) => highlighted.push(keys));
  const panel = new SceneGraphPanel(new FakeDocument(), bus);
  panel.showGraph(SceneGraph.of(FACTS));
  return { panel, highlighted, root: panel.panel.element };
}

const labelButtons = (root) => root.findAll((element) => element.className === 'graph-label');
const shownNodes = (root) => root.findAll((element) => element.className === 'graph-node').map((element) => element.dataset.node);

test('the tree starts unfolded down to the models and counts what the scene holds', () => {
  const { root } = openPanel();
  assert.equal(UNFOLDED_DEPTH, 2);
  assert.equal(root.children[0].textContent, '2 models · 4 links · 1 object · 2 part annotations');
  assert.deepEqual(shownNodes(root), ['world', 'model:arm', 'link:arm/base', 'model:environment', 'link:environment/table', 'group:objects', 'object:k-milk', 'group:parts', 'part:left_arm', 'part:left_gripper']);
});

test('choosing a node unfolds the tree to it, shows its relations and lights it up', () => {
  const { panel, highlighted, root } = openPanel();
  labelButtons(root).find((button) => button.dataset.node === 'part:left_gripper').dispatch('click');
  assert.equal(panel.chosen, 'part:left_gripper');
  assert.deepEqual(highlighted, [['gripper']]);
  const details = root.children[3];
  const related = details.findAll((element) => element.className === 'graph-label').map((element) => element.dataset.node);
  assert.deepEqual(related, ['link:arm/gripper', 'part:left_arm']);
  details.findAll((element) => element.className === 'graph-label')[0].dispatch('click');
  assert.equal(panel.chosen, 'link:arm/gripper');
  assert.ok(shownNodes(root).includes('link:arm/gripper'), 'the tree unfolds down to the chosen link');
});

test('a selection in the 3D view chooses its node', () => {
  const { panel, highlighted } = openPanel();
  panel.reveal({ [SelectionKey.KIND]: SelectionKind.LINK, [SelectionKey.MODEL]: 'arm', [SelectionKey.NAME]: 'upper' });
  assert.equal(panel.chosen, 'link:arm/upper');
  assert.deepEqual(highlighted, [['upper']]);
  panel.reveal(null);
  assert.equal(panel.chosen, 'link:arm/upper');
});

test('the filter shows the matching nodes with the way down to them', () => {
  const { root } = openPanel();
  const filter = root.children[1];
  filter.value = 'milk';
  filter.dispatch('input');
  assert.deepEqual(shownNodes(root), ['world', 'group:objects', 'object:k-milk']);
});
