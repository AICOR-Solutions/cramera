import { test } from 'node:test';
import assert from 'node:assert/strict';

import { EventBus } from '../../src/cramera/web/core/event-bus.js';
import { SceneGraphPanel, UNFOLDED_DEPTH } from '../../src/cramera/web/panels/scene-graph-panel.js';
import { SelectionKey, SelectionKind, ViewerEvent } from '../../src/cramera/web/protocol.js';
import { ClassField, FixedNode, NodeKind, SceneGraph } from '../../src/cramera/web/scene/scene-graph.js';
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

/**
 * The classes the recorded world held the cell's entities as.
 */
const CLASSES = Object.freeze({
  world: 'semantic_digital_twin.world.World',
  models: { arm: 'semantic_digital_twin.robots.cell.CellArm' },
  bodies: { base: 'semantic_digital_twin.world_description.world_entity.Body', 'milk': 'semantic_digital_twin.world_description.world_entity.Body' },
  connections: { shoulder: 'semantic_digital_twin.world_description.connections.RevoluteConnection' },
  annotations: { left_arm: 'semantic_digital_twin.robots.cell.CellLeftArm' },
});

/**
 * The module of the semantic annotations' classes.
 */
const ANNOTATIONS_MODULE = 'semantic_digital_twin.semantic_annotations.semantic_annotations';

/**
 * The cell with its table and the milk annotated, and a shelf whose board the scene
 * does not show.
 */
const ANNOTATED = Object.freeze({
  ...FACTS,
  annotations: [
    { name: 'milk', classPath: `${ANNOTATIONS_MODULE}.Milk`, bodies: ['milk'] },
    { name: 'shelf', classPath: `${ANNOTATIONS_MODULE}.Shelf`, bodies: ['shelf_board'] },
    { name: 'table', classPath: `${ANNOTATIONS_MODULE}.Table`, bodies: ['table', 'milk'] },
  ],
});

const labels = (nodes) => nodes.map((node) => node.label);
const classesOf = (node) => node.classes.map((nodeClass) => [nodeClass.field, nodeClass.name]);

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

test('a node names the classes the recorded world held its entity as', () => {
  const graph = SceneGraph.of({ ...FACTS, classes: CLASSES });
  assert.deepEqual(classesOf(graph.node(FixedNode.WORLD)), [[ClassField.OWN, 'World']]);
  assert.deepEqual(classesOf(graph.node('model:arm')), [[ClassField.OWN, 'CellArm']]);
  assert.deepEqual(classesOf(graph.node('model:environment')), []);
  assert.deepEqual(classesOf(graph.node('link:arm/base')), [[ClassField.OWN, 'Body']]);
  assert.deepEqual(classesOf(graph.node('link:arm/upper')), [[ClassField.JOINT, 'RevoluteConnection']]);
  assert.deepEqual(classesOf(graph.node('object:k-milk')), [[ClassField.OWN, 'Body']]);
  assert.deepEqual(classesOf(graph.node('part:left_arm')), [[ClassField.OWN, 'CellLeftArm']]);
  assert.equal(graph.node('part:left_arm').classes[0].path, CLASSES.annotations.left_arm);
  assert.deepEqual(classesOf(SceneGraph.of(FACTS).node(FixedNode.WORLD)), []);
});

test('a model and a group light up everything they hold', () => {
  const graph = SceneGraph.of(FACTS);
  assert.deepEqual(graph.node('model:arm').keys, ['base', 'gripper', 'upper']);
  assert.deepEqual(graph.node(FixedNode.OBJECTS).keys, ['k-milk']);
  assert.deepEqual(graph.node(FixedNode.PARTS).keys, ['base', 'upper', 'gripper']);
  assert.deepEqual(graph.node(FixedNode.WORLD).keys, []);
});

test('a scene without objects or parts has no groups for them', () => {
  const graph = SceneGraph.of({ name: 'bare', models: [], objects: [], parts: [] });
  assert.deepEqual(graph.children(FixedNode.WORLD), []);
  assert.equal(SceneGraph.of({ ...FACTS, annotations: [] }).node(FixedNode.ANNOTATIONS), undefined);
});

test('a semantic annotation lights up its links and objects and names its class', () => {
  const graph = SceneGraph.of(ANNOTATED);
  assert.deepEqual(labels(graph.children(FixedNode.WORLD)), ['arm', 'environment', 'Free objects', 'Robot parts', 'Semantic annotations']);
  assert.deepEqual(labels(graph.children(FixedNode.ANNOTATIONS)), ['milk', 'shelf', 'table']);
  const [milk, shelf, table] = graph.children(FixedNode.ANNOTATIONS);
  assert.equal(table.kind, NodeKind.ANNOTATION);
  assert.deepEqual(table.keys, ['table', 'k-milk']);
  assert.deepEqual(table.references.map((reference) => [reference.field, reference.target]), [['body', 'link:environment/table'], ['body', 'object:k-milk']]);
  assert.deepEqual(table.fields, [['Bodies', '2']]);
  assert.deepEqual(classesOf(table), [[ClassField.OWN, 'Table']]);
  assert.equal(table.classes[0].path, `${ANNOTATIONS_MODULE}.Table`);
  assert.deepEqual(milk.keys, ['k-milk']);
  assert.deepEqual(shelf.keys, ['shelf_board'], 'a body the scene does not show is still lit up by name');
  assert.deepEqual(shelf.references, []);
  assert.deepEqual(graph.referencedBy('object:k-milk').map((entry) => entry.source.label), ['milk', 'table']);
  assert.deepEqual(graph.node(FixedNode.ANNOTATIONS).keys, ['k-milk', 'shelf_board', 'table']);
  assert.deepEqual(graph.counts().get(NodeKind.ANNOTATION), 3);
});

// %% panel

/**
 * Where the panel's class links lead in the tests.
 */
const classAddress = (path) => `ontology.html#${path}`;

function openPanel() {
  const bus = new EventBus();
  const highlighted = [];
  const focused = [];
  bus.subscribe(ViewerEvent.ENTITY_HIGHLIGHTED, (keys) => highlighted.push(keys));
  bus.subscribe(ViewerEvent.FOCUS_REQUESTED, (keys) => focused.push(keys));
  const panel = new SceneGraphPanel(new FakeDocument(), bus, classAddress);
  panel.showGraph(SceneGraph.of({ ...FACTS, classes: CLASSES }));
  return { panel, highlighted, focused, root: panel.panel.element };
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

test('a chosen node links each of its classes to the ontology page', () => {
  const { panel, root } = openPanel();
  panel.choose('link:arm/upper');
  const [link] = root.findAll((element) => element.className === 'graph-class');
  assert.equal(link.textContent, 'RevoluteConnection');
  assert.equal(link.href, classAddress(CLASSES.connections.shoulder));
  assert.equal(link.target, 'cramera-ontology');
  panel.choose('model:environment');
  assert.deepEqual(root.findAll((element) => element.className === 'graph-class'), []);
});

test('the camera moves onto a chosen node on request', () => {
  const { panel, focused, root } = openPanel();
  panel.choose('part:left_arm');
  root.findAll((element) => element.className === 'graph-focus')[0].dispatch('click');
  assert.deepEqual(focused, [['base', 'upper']]);
  panel.choose(FixedNode.WORLD);
  assert.deepEqual(root.findAll((element) => element.className === 'graph-focus'), [], 'the world lights nothing up to move onto');
});

test('a selection in the 3D view chooses its node', () => {
  const { panel, highlighted } = openPanel();
  panel.reveal({ [SelectionKey.KIND]: SelectionKind.LINK, [SelectionKey.MODEL]: 'arm', [SelectionKey.NAME]: 'upper' });
  assert.equal(panel.chosen, 'link:arm/upper');
  assert.deepEqual(highlighted, [['upper']]);
  panel.reveal(null);
  assert.equal(panel.chosen, 'link:arm/upper');
});

test('choosing a semantic annotation lights up its bodies and links its class', () => {
  const bus = new EventBus();
  const highlighted = [];
  bus.subscribe(ViewerEvent.ENTITY_HIGHLIGHTED, (keys) => highlighted.push(keys));
  const panel = new SceneGraphPanel(new FakeDocument(), bus, classAddress);
  panel.showGraph(SceneGraph.of(ANNOTATED));
  const root = panel.panel.element;
  assert.equal(root.children[0].textContent, '2 models · 4 links · 1 object · 2 part annotations · 3 semantic annotations');
  assert.ok(shownNodes(root).includes(`annotation:${ANNOTATIONS_MODULE}.Table:table`), 'the annotations show unfolded');
  labelButtons(root).find((button) => button.dataset.node === `annotation:${ANNOTATIONS_MODULE}.Table:table`).dispatch('click');
  assert.deepEqual(highlighted, [['table', 'k-milk']]);
  const [link] = root.findAll((element) => element.className === 'graph-class');
  assert.equal(link.textContent, 'Table');
  assert.equal(link.href, classAddress(`${ANNOTATIONS_MODULE}.Table`));
  const related = root.children[3].findAll((element) => element.className === 'graph-label').map((element) => element.dataset.node);
  assert.deepEqual(related, ['link:environment/table', 'object:k-milk']);
});

test('the filter shows the matching nodes with the way down to them', () => {
  const { root } = openPanel();
  const filter = root.children[1];
  filter.value = 'milk';
  filter.dispatch('input');
  assert.deepEqual(shownNodes(root), ['world', 'group:objects', 'object:k-milk']);
});
