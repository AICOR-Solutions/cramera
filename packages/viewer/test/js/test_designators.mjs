import { test } from 'node:test';
import assert from 'node:assert/strict';

import { EventBus } from '../../src/cramera/web/core/event-bus.js';
import {
  actionAt,
  AnswerOrigin,
  Filling,
  NodePhase,
  nodeAtFrame,
  phaseOf,
  roleRows,
  rowsOfKey,
  runningNode,
  slotResolutions,
  stepsNaming,
  stepsOfAction,
  topLevelActions,
  whenAsked,
} from '../../src/cramera/web/designators/designator-chain.js';
import { DesignatorsPanel, NO_ROLES } from '../../src/cramera/web/panels/designators-panel.js';
import {
  DesignatorRole,
  PlanNodeKey,
  PlanNodeKind,
  QueryStepKey,
  QueryStepsKey,
  RoleEntityKey,
  RoleSlotKey,
  RoleSource,
  SceneKey,
  SelectionKey,
  StepPhase,
  ViewerEvent,
} from '../../src/cramera/web/protocol.js';
import { FakeDocument } from './support/fake-document.mjs';

// %% a small recorded run: the PR2 loads a vessel into a centrifuge holder

const PR2_LINKS = ['pr2/base_link', 'pr2/l_shoulder_pan_link', 'pr2/l_gripper_palm_link'];
const ARM_LINKS = ['pr2/l_shoulder_pan_link', 'pr2/l_gripper_palm_link'];
const VESSEL = 'b3fa93d4-39af-477a-bbac-5feaee00ac3c';

const entity = (name, type, keys) => ({ [RoleEntityKey.NAME]: name, [RoleEntityKey.TYPE]: type, [RoleEntityKey.KEYS]: keys });
const slot = (field, role, value, entities = [], extra = {}) => ({
  [RoleSlotKey.FIELD]: field,
  [RoleSlotKey.ROLE]: role,
  [RoleSlotKey.SOURCE]: RoleSource.FIELD,
  [RoleSlotKey.VALUE]: value,
  [RoleSlotKey.ENTITIES]: entities,
  ...extra,
});
const AGENT = slot('robot', DesignatorRole.AGENT, 'PR2', [entity('PR2', 'PR2', PR2_LINKS)], { [RoleSlotKey.SOURCE]: RoleSource.CONTEXT });
const ARM = slot('arm', DesignatorRole.EFFECTOR, 'PR2LeftArm', [entity('PR2LeftArm', 'PR2LeftArm', ARM_LINKS)]);
const OBJECT = slot('grasp.graspable', DesignatorRole.OBJECT, 'Container', [entity('tube_amber', 'Container', [VESSEL])]);
const HOLDER = slot('target_location', DesignatorRole.LOCATION, '0.000, 0.052, 0.020', [], {
  [RoleSlotKey.REFERENCE]: entity('laboratory_centrifuge_rotor', 'Body', ['laboratory_centrifuge_rotor']),
});

const node = (identifier, kind, label, start, end, roles = [], children = [], status = 'SUCCEEDED') => ({
  [PlanNodeKey.IDENTIFIER]: identifier,
  [PlanNodeKey.KIND]: kind,
  [PlanNodeKey.LABEL]: label,
  [PlanNodeKey.STATUS]: status,
  [PlanNodeKey.START]: start,
  [PlanNodeKey.END]: end,
  [PlanNodeKey.ROLES]: roles,
  [PlanNodeKey.CHILDREN]: children,
});

const PICK = node('plan_node_1', PlanNodeKind.ACTION, 'VesselPickUpAction', 10, 40, [AGENT, ARM, OBJECT], [
  node('plan_node_2', PlanNodeKind.MOTION, 'MoveGripperMotion', null, null, [slot('gripper', DesignatorRole.EFFECTOR, 'PR2LeftGripper', [entity('PR2LeftGripper', 'PR2LeftGripper', ['pr2/l_gripper_palm_link'])])]),
]);
const PLACE = node('plan_node_3', PlanNodeKind.ACTION, 'RackPlaceAction', 50, 80, [AGENT, ARM, HOLDER], [], 'FAILED');
const ROOT = node('plan_node_0', PlanNodeKind.SEQUENCE, 'SequentialNode', 10, 80, [], [PICK, PLACE]);

const step = (number, question, entities, frame, phase = StepPhase.EXPANSION, planNode = null) => ({
  [QueryStepKey.NUMBER]: number,
  [QueryStepKey.PHASE]: phase,
  [QueryStepKey.QUESTION]: { text: question },
  [QueryStepKey.ANSWERS]: entities.map((each) => each[RoleEntityKey.NAME]),
  [QueryStepKey.ENTITIES]: entities,
  [QueryStepKey.FRAME]: frame,
  [QueryStepKey.PLAN_NODE]: planNode,
  [QueryStepKey.BACKEND]: { name: 'EntityQueryLanguageBackend', source: 'working memory' },
});
const STEPS = [
  step(0, 'Find the unique PR2', [entity('PR2', 'PR2', PR2_LINKS)], 0, StepPhase.SETUP),
  step(1, "Find the unique Body named 'tube_amber'", [entity('tube_amber', 'Body', [VESSEL])], 0),
  step(2, 'Find a Body asked while placing', [entity('stopper', 'Body', ['c710'])], 55, StepPhase.EXECUTION, 'plan_node_3'),
  step(3, "Find the Body named 'tube_amber' again, after the pick-up", [entity('tube_amber', 'Body', [VESSEL])], 45, StepPhase.EXECUTION),
];

// %% phases

test('a node is pending before its frames, running within them and ends with its recorded status', () => {
  assert.equal(phaseOf(PICK, 5, null).phase, NodePhase.PENDING);
  assert.equal(phaseOf(PICK, 10, null).phase, NodePhase.RUNNING);
  assert.equal(phaseOf(PICK, 41, null).phase, NodePhase.SUCCEEDED);
  assert.equal(phaseOf(PLACE, 81, null).phase, NodePhase.FAILED);
});

test('a motion without frames of its own takes its action’s phase, marked as inferred', () => {
  const running = nodeAtFrame(PICK, 20);
  assert.equal(running.children[0].phase, NodePhase.RUNNING);
  assert.equal(running.children[0].inferred, true);
  assert.equal(runningNode(running).identifier, 'plan_node_1');
  assert.equal(nodeAtFrame(PICK, 3).children[0].phase, NodePhase.PENDING);
  assert.equal(nodeAtFrame(PICK, 60).children[0].phase, NodePhase.SUCCEEDED);
});

test('the top-level action is the one the frame falls in, else the last one started', () => {
  assert.deepEqual(topLevelActions([ROOT]).map((action) => action[PlanNodeKey.LABEL]), ['VesselPickUpAction', 'RackPlaceAction']);
  assert.equal(actionAt([ROOT], 0), PICK);
  assert.equal(actionAt([ROOT], 30), PICK);
  assert.equal(actionAt([ROOT], 45), PICK);
  assert.equal(actionAt([ROOT], 60), PLACE);
  assert.equal(actionAt([], 0), null);
});

// %% role → entity

test('every entity a role names is a row once, with its type, field and designator; a pose names its frame', () => {
  const rows = roleRows(PLACE);
  assert.deepEqual(rows.map((row) => [row.name, row.type, row.role, row.field, row.reference]), [
    ['PR2', 'PR2', DesignatorRole.AGENT, 'robot', false],
    ['PR2LeftArm', 'PR2LeftArm', DesignatorRole.EFFECTOR, 'arm', false],
    ['laboratory_centrifuge_rotor', 'Body', DesignatorRole.LOCATION, 'target_location', true],
  ]);
  assert.deepEqual(roleRows(PICK).map((row) => row.designator), ['VesselPickUpAction', 'VesselPickUpAction', 'VesselPickUpAction', 'MoveGripperMotion']);
});

test('a body selected in the 3D view finds the rows of every entity it belongs to', () => {
  const rows = roleRows(PICK);
  assert.deepEqual(rowsOfKey(rows, VESSEL).map((row) => row.name), ['tube_amber']);
  assert.deepEqual(rowsOfKey(rows, 'pr2/l_gripper_palm_link').map((row) => row.name), ['PR2', 'PR2LeftArm', 'PR2LeftGripper']);
  assert.deepEqual(rowsOfKey(rows, 'laboratory_room'), []);
});

// %% entity → query → answer → frame

test('a role is filled by a query when one of its answers is the same entity, not a part of one', () => {
  assert.deepEqual(stepsNaming(AGENT, STEPS).map((each) => each[QueryStepKey.NUMBER]), [0]);
  assert.deepEqual(stepsNaming(ARM, STEPS), [], 'the arm is a part of the robot the query answered, not an answer');
  assert.deepEqual(stepsNaming(OBJECT, STEPS).map((each) => each[QueryStepKey.NUMBER]), [1, 3], 'a container and its vessel body light up the same keys');
});

test('only queries asked before a designator started fill its roles; the rest were written or computed by the plan', () => {
  const pick = slotResolutions(PICK, STEPS);
  assert.deepEqual(pick.map((each) => [each.slot[RoleSlotKey.FIELD], each.filling, each.steps.map((s) => s[QueryStepKey.NUMBER])]), [
    ['robot', Filling.QUERIED, [0]],
    ['arm', Filling.WRITTEN, []],
    ['grasp.graspable', Filling.QUERIED, [1]],
  ]);
  const place = slotResolutions(PLACE, STEPS);
  assert.equal(place[2].filling, Filling.COMPUTED);
  assert.deepEqual(slotResolutions(PLACE, []).map((each) => each.filling), [Filling.FROM_CONTEXT, Filling.WRITTEN, Filling.COMPUTED]);
});

test('an action’s queries are those naming its roles’ entities and those asked while it ran, in the order asked, with when they were asked', () => {
  assert.deepEqual(stepsOfAction(PICK, STEPS).map((each) => each[QueryStepKey.NUMBER]), [0, 1]);
  assert.deepEqual(stepsOfAction(PLACE, STEPS).map((each) => each[QueryStepKey.NUMBER]), [0, 2]);
  assert.equal(whenAsked(STEPS[1], PICK), 'while the plans were built, before any motion');
  assert.equal(whenAsked(STEPS[2], PLACE), 'while the action ran');
});

// %% the panel

const SCENE = {
  description: { [SceneKey.PLAN_TREES]: [ROOT] },
  querySteps: { [QueryStepsKey.STEPS]: STEPS },
};

test('the panel follows the playback frame: action, phases and the answers marked as recorded', () => {
  const document = new FakeDocument();
  const bus = new EventBus();
  const panel = new DesignatorsPanel(document, bus);
  panel.show(SCENE);
  bus.publish(ViewerEvent.FRAME_CHANGED, 20);
  assert.equal(panel.action, PICK);
  const text = panel.panel.element.innerText;
  assert.match(text, /VesselPickUpAction/);
  assert.match(text, /running/);
  assert.match(text, /Find the unique PR2/);
  assert.match(text, /RECORDED/);
  assert.doesNotMatch(text, /LIVE/);
  bus.publish(ViewerEvent.FRAME_CHANGED, 85);
  assert.equal(panel.action, PLACE);
  assert.match(panel.panel.element.innerText, /failed/);
});

test('answers a running process published are marked live', () => {
  const panel = new DesignatorsPanel(new FakeDocument(), new EventBus());
  panel.show(SCENE);
  panel.showSteps(SCENE.querySteps, AnswerOrigin.LIVE);
  assert.match(panel.panel.element.innerText, /LIVE/);
  assert.doesNotMatch(panel.panel.element.innerText, /RECORDED/);
});

test('a row lights its entity up in the 3D view, and a body selected there marks its row', () => {
  const document = new FakeDocument();
  const bus = new EventBus();
  const highlighted = [];
  bus.subscribe(ViewerEvent.ENTITY_HIGHLIGHTED, (keys) => highlighted.push(keys));
  const panel = new DesignatorsPanel(document, bus);
  panel.show(SCENE);
  bus.publish(ViewerEvent.FRAME_CHANGED, 20);
  const vesselRow = panel.panel.element.findAll((each) => each.dataset.keys === VESSEL)[0];
  vesselRow.click();
  assert.deepEqual(highlighted.at(-1), [VESSEL]);
  bus.publish(ViewerEvent.ENTITY_SELECTED, { [SelectionKey.KIND]: 'link', [SelectionKey.NAME]: 'pr2/base_link' });
  assert.deepEqual(panel.selected, PR2_LINKS);
  const marked = panel.panel.element.findAll((each) => (each.className ?? '').includes('role-row selected'));
  assert.deepEqual(marked.map((each) => each.dataset.keys), [PR2_LINKS.join(' ')]);
});

test('a recording written before roles says so instead of showing an empty table', () => {
  const old = node('plan_node_1', PlanNodeKind.ACTION, 'VesselPickUpAction', 0, 9);
  delete old[PlanNodeKey.ROLES];
  const panel = new DesignatorsPanel(new FakeDocument(), new EventBus());
  panel.show({ description: { [SceneKey.PLAN_TREES]: [old] }, querySteps: null });
  assert.match(panel.panel.element.innerText, new RegExp(NO_ROLES.slice(0, 40)));
});
