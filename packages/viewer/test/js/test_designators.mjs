import { test } from 'node:test';
import * as THREE from 'three';
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
  runningTarget,
  targetOf,
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
import { TARGET_VIEW, TargetFollow } from '../../src/cramera/web/scene/target-follow.js';
import { TargetMarker, WORLD_FRAMES } from '../../src/cramera/web/scene/target-marker.js';
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
  [RoleSlotKey.PLACE]: 'centrifuge C4',
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

test('a location the task named carries the place’s name into its row, its slot and its resolution', () => {
  const [, , holder] = roleRows(PLACE);
  assert.equal(holder.place, 'centrifuge C4');
  assert.equal(roleRows(PICK).every((row) => row.place === null), true);
  const panel = new DesignatorsPanel(new FakeDocument(), new EventBus());
  panel.show(SCENE);
  panel.showFrame(60);
  const places = panel.panel.element.findAll((each) => each.className === 'role-place').map((each) => each.textContent);
  assert.deepEqual(places, ['centrifuge C4', 'centrifuge C4', 'centrifuge C4']);
});

test('motions with frames of their own show their own phase, and the running one is current', () => {
  const reach = node('n_reach', PlanNodeKind.MOTION, 'MoveToolCenterPointMotion', 10, 19);
  const close = node('n_close', PlanNodeKind.MOTION, 'MoveGripperMotion', 20, 25);
  const attach = node('n_attach', PlanNodeKind.ATTACHMENT, 'ReAttachNode', null, null);
  const steps = node('n_steps', PlanNodeKind.SEQUENCE, 'SequentialNode', 10, 25, [], [reach, close, attach], 'CREATED');
  const pick = node('n_pick', PlanNodeKind.ACTION, 'VesselPickUpAction', 10, 25, [], [steps]);
  const during = nodeAtFrame(pick, 22);
  const [stepsAt] = during.children;
  assert.deepEqual(stepsAt.children.map((each) => [each.phase, each.inferred]), [
    [NodePhase.SUCCEEDED, false],
    [NodePhase.RUNNING, false],
    [NodePhase.RUNNING, true],
  ]);
  assert.equal(runningNode(during).identifier, 'n_close');
  const after = nodeAtFrame(pick, 30);
  assert.equal(after.children[0].phase, NodePhase.ENDED, 'a sequence that ran has no status of its own');
  assert.equal(after.children[0].inferred, false);
});

// %% the running step's target

const ROTOR_FRAME = entity('laboratory_centrifuge_rotor', 'Body', ['laboratory_centrifuge_rotor']);
const lower = node('n_lower', PlanNodeKind.MOTION, 'MoveToolCenterPointMotion', 30, 39, [
  slot('target', DesignatorRole.LOCATION, '0.000, -0.072, 0.143', [], { [RoleSlotKey.REFERENCE]: ROTOR_FRAME, [RoleSlotKey.POSE]: [0, -0.072, 0.143, 0, 0, 0, 1] }),
  ARM,
]);
const open = node('n_open', PlanNodeKind.MOTION, 'HeldToolGripperMotion', 40, 45, [slot('gripper', DesignatorRole.EFFECTOR, 'PR2LeftGripper', [entity('PR2LeftGripper', 'PR2LeftGripper', ['pr2/l_gripper_palm_link'])])]);
const turn = node('n_turn', PlanNodeKind.MOTION, 'MechanismMotion', 46, 50, [slot('part', DesignatorRole.OBJECT, 'laboratory_centrifuge_lid', [entity('laboratory_centrifuge_lid', 'Body', ['laboratory_centrifuge_lid'])]), ARM]);
const LOAD = node('n_load', PlanNodeKind.ACTION, 'RackPlaceAction', 30, 50, [AGENT, OBJECT, {
  ...HOLDER,
  [RoleSlotKey.POSE]: [0, -0.072, 0.008, 0, 0, 0, 1],
}], [lower, open, turn]);

test('a step’s target is its location in its reference’s frame, else the entity it acts on', () => {
  const lowering = targetOf(lower);
  assert.deepEqual(lowering.keys, ['laboratory_centrifuge_rotor']);
  assert.deepEqual(lowering.pose, [0, -0.072, 0.143, 0, 0, 0, 1]);
  assert.equal(lowering.label, 'MoveToolCenterPointMotion · target');
  assert.equal(targetOf(LOAD).label, 'RackPlaceAction · target_location · centrifuge C4');
  const turning = targetOf(turn);
  assert.deepEqual([turning.keys, turning.pose], [['laboratory_centrifuge_lid'], null]);
  assert.equal(targetOf(open), null);
});

test('the running motion’s target is marked, or its action’s while the motion has none', () => {
  const marked = (frame) => {
    const tree = nodeAtFrame(LOAD, frame);
    return runningTarget(runningNode(tree), tree);
  };
  assert.equal(marked(35).label, 'MoveToolCenterPointMotion · target');
  assert.equal(marked(42).label, 'RackPlaceAction · target_location · centrifuge C4');
  assert.equal(marked(48).frame, 'laboratory_centrifuge_lid');
  assert.equal(marked(60), null);
});

test('the panel tells the 3D view the running step’s target once each time it changes', () => {
  const bus = new EventBus();
  const marks = [];
  bus.subscribe(ViewerEvent.TARGET_MARKED, (target) => marks.push(target?.label ?? null));
  const panel = new DesignatorsPanel(new FakeDocument(), bus);
  panel.show({ description: { [SceneKey.PLAN_TREES]: [LOAD] }, querySteps: null });
  for (const frame of [31, 32, 33, 41, 47, 60]) bus.publish(ViewerEvent.FRAME_CHANGED, frame);
  assert.deepEqual(marks, [
    'MoveToolCenterPointMotion · target',
    'RackPlaceAction · target_location · centrifuge C4',
    'MechanismMotion · part · laboratory_centrifuge_lid',
    null,
  ]);
});

test('the mark is attached to the body its target is given in, at the target’s pose', () => {
  const content = new THREE.Group();
  const rotor = Object.assign(new THREE.Object3D(), { isURDFLink: true, urdfName: 'laboratory_centrifuge_rotor' });
  const rack = new THREE.Group();
  rack.userData.objectKey = 'rack-key';
  content.add(rotor, rack);
  const marker = new TargetMarker({ content });
  marker.show({ keys: ['laboratory_centrifuge_rotor'], frame: 'laboratory_centrifuge_rotor', pose: [0, -0.072, 0.143, 0, 0, 0, 1], label: 'lowering' });
  assert.equal(marker.mark.parent, rotor);
  assert.deepEqual(marker.mark.position.toArray(), [0, -0.072, 0.143]);
  marker.show({ keys: ['rack-key'], frame: 'laboratory_rack', pose: null, label: 'rack' });
  assert.equal(marker.mark.parent, rack);
  assert.deepEqual(marker.mark.position.toArray(), [0, 0, 0]);
  marker.show({ keys: ['map'], frame: WORLD_FRAMES[0], pose: [1, 2, 0, 0, 0, 0, 1], label: 'drive' });
  assert.equal(marker.mark.parent, content, 'the map is the frame the content is given in');
  marker.show({ keys: ['unknown'], frame: 'unknown', pose: null, label: 'nowhere' });
  assert.equal(marker.mark.parent, null);
  marker.show(null);
  assert.equal(marker.mark.parent, null);
});

test('lighting up the body a mark is attached to leaves the mark as it is', async () => {
  const { ownMeshes } = await import('../../src/cramera/web/scene/scene-highlights.js');
  const rotor = Object.assign(new THREE.Object3D(), { isURDFLink: true, urdfName: 'laboratory_centrifuge_rotor' });
  const body = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.1, 0.1), new THREE.MeshBasicMaterial());
  rotor.add(body);
  const marker = new TargetMarker({ content: rotor });
  marker.show({ keys: ['laboratory_centrifuge_rotor'], frame: 'laboratory_centrifuge_rotor', pose: null, label: 'here' });
  assert.deepEqual(ownMeshes(rotor), [body]);
});

// %% the camera following the target

/**
 * @returns {{view: Object, glides: Array<THREE.Box3>, glide: Object, gripper: THREE.Object3D, marker: TargetMarker}}
 *   A view with a camera, a glide that notes where it goes, and a mark on a gripper.
 */
function followingScene() {
  const content = new THREE.Group();
  const gripper = Object.assign(new THREE.Object3D(), { isURDFLink: true, urdfName: 'pr2/l_gripper_tool_frame' });
  content.add(gripper);
  const view = { content, camera: { position: new THREE.Vector3(2, 0, 1), up: new THREE.Vector3(0, 1, 0) }, controls: { target: new THREE.Vector3(0, 0, 1) }, requestRender() {} };
  const glides = [];
  const glide = { gliding: false, looking: null, glideTo(box, seconds, looking) { glides.push(box); this.looking = looking; return true; } };
  const marker = new TargetMarker(view);
  marker.show({ keys: ['pr2/l_gripper_tool_frame'], frame: 'pr2/l_gripper_tool_frame', pose: [-0.07, 0, 0, 0, 0, 0, 1], label: 'back off' });
  return { view, glides, glide, gripper, marker };
}

test('following the target glides onto a box around the mark each time the target changes', () => {
  const { view, glides, glide, marker } = followingScene();
  const follow = new TargetFollow(view, marker.mark, glide);
  assert.equal(follow.aim(), false, 'not following: the camera stays');
  follow.following = true;
  assert.equal(follow.aim(), true);
  const box = glides.at(-1);
  assert.deepEqual(box.getCenter(new THREE.Vector3()).toArray().map((each) => +each.toFixed(6)), [-0.07, 0, 0]);
  assert.equal(+box.getSize(new THREE.Vector3()).x.toFixed(6), TARGET_VIEW);
  const elevation = THREE.MathUtils.radToDeg(Math.asin(glide.looking.y));
  assert.equal(Math.round(elevation), 55, 'from above');
  assert.ok(glide.looking.x > 0 && Math.abs(glide.looking.z) < 1e-9, 'from the side the camera looked from');
  marker.show(null);
  assert.equal(follow.aim(), false, 'no target: nothing to glide onto');
});

test('the camera moves with a mark whose body moves, but not while it glides or does not follow', () => {
  const { view, glide, gripper, marker } = followingScene();
  const follow = new TargetFollow(view, marker.mark, glide);
  follow.following = true;
  follow.aim();
  gripper.position.set(0.1, 0.2, 0);
  gripper.updateMatrixWorld(true);
  follow.follow();
  assert.deepEqual(view.camera.position.toArray().map((each) => +each.toFixed(6)), [2.1, 0.2, 1]);
  assert.deepEqual(view.controls.target.toArray().map((each) => +each.toFixed(6)), [0.1, 0.2, 1]);
  glide.gliding = true;
  gripper.position.set(0.3, 0.2, 0);
  gripper.updateMatrixWorld(true);
  follow.follow();
  assert.deepEqual(view.camera.position.toArray().map((each) => +each.toFixed(6)), [2.1, 0.2, 1], 'the glide moves the camera');
  glide.gliding = false;
  follow.following = false;
  gripper.position.set(0.5, 0.2, 0);
  gripper.updateMatrixWorld(true);
  follow.follow();
  assert.deepEqual(view.camera.position.toArray().map((each) => +each.toFixed(6)), [2.1, 0.2, 1]);
});
