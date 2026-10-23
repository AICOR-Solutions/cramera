import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  ActionCatalogKey,
  ActionFieldKey,
  ActionSchemaKey,
  DestinationKey,
  ObjectModelKey,
  PlacementMode,
  PlanBuilderCatalogKey,
  PlanBuilderLimitsKey,
  PlanKey,
  PlannedObjectKey,
  PlannedRobotKey,
  PlanStepKey,
  RobotModelKey,
  StepConstraintKey,
} from 'cramera-viewer/protocol.js';
import { IdentityPrefix, NEW_PLAN_NAME, PlanRefused, PlanState } from '../../src/cramera_plan_builder/web/builder/plan-state.js';
import { PlanPose } from '../../src/cramera_plan_builder/web/builder/poses.js';

const read = (name) => JSON.parse(readFileSync(new URL(name, import.meta.url), 'utf8'));
const actions = read('../dataset/actions.json');
const catalog = () => ({
  ...read('dataset/catalog.json'),
  [PlanBuilderCatalogKey.ACTIONS]: actions[ActionCatalogKey.ACTIONS],
  [PlanBuilderCatalogKey.FAILED_ACTION_MODULES]: actions[ActionCatalogKey.FAILED_MODULES],
});
const model = (state, name) => state.catalog[PlanBuilderCatalogKey.ROBOTS].find((entry) => entry[RobotModelKey.NAME] === name);
const objectModel = (state, index) => state.catalog[PlanBuilderCatalogKey.OBJECTS][index];
const values = (state, identifier) => state.step(identifier)[PlanStepKey.VALUES];
const fieldOf = (state, action, name) => state.schema(action)[ActionSchemaKey.FIELDS].find((field) => field[ActionFieldKey.NAME] === name);

// %% new plans

test('a new plan starts with one robot of the model offering the most actions', () => {
  const state = PlanState.empty(catalog(), 'lab');
  const robot = state.activeRobot();
  assert.equal(state.field(PlanKey.NAME), NEW_PLAN_NAME);
  assert.equal(state.field(PlanKey.ENVIRONMENT), 'lab');
  assert.equal(state.robots().length, 1);
  assert.equal(robot[PlannedRobotKey.MODEL], 'Armar7');
  assert.equal(robot[PlannedRobotKey.IDENTIFIER], `${IdentityPrefix.ROBOT}1`);
});

test('a new plan starts with the model the person used last', () => {
  const state = PlanState.empty(catalog(), null, 'Tracy');
  assert.equal(state.activeRobot()[PlannedRobotKey.MODEL], 'Tracy');
  assert.equal(state.field(PlanKey.ENVIRONMENT), '');
});

test('the document names the edited robot as the one that performs', () => {
  const state = PlanState.empty(catalog(), 'lab');
  const second = state.addRobot('Tracy');
  assert.equal(state.document[PlanKey.SELECTED_ROBOT], second);
  state.selectRobot(`${IdentityPrefix.ROBOT}1`);
  assert.equal(state.document[PlanKey.SELECTED_ROBOT], `${IdentityPrefix.ROBOT}1`);
});

// %% actions

test('a robot is offered every available action whose enumerations it can fill', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const offered = state.offeredActions(state.activeRobot()).map((schema) => schema[ActionSchemaKey.NAME]);
  const available = state.actions().filter((schema) => schema[ActionSchemaKey.AVAILABLE]).map((schema) => schema[ActionSchemaKey.NAME]);
  assert.deepEqual(offered, available);
  const unavailable = state.actions().find((schema) => !schema[ActionSchemaKey.AVAILABLE]);
  assert.equal(state.refusal(state.activeRobot(), unavailable), unavailable[ActionSchemaKey.UNAVAILABLE_REASON]);
});

test('a robot without a torso is not offered moving the torso', () => {
  const state = PlanState.empty(catalog(), 'lab', 'Tracy');
  const torso = state.schema('MoveTorsoAction');
  assert.match(state.refusal(state.activeRobot(), torso), /TorsoState/);
  assert.throws(() => state.addStep('MoveTorsoAction'), PlanRefused);
  assert.throws(() => state.addStep('DanceAction'), PlanRefused);
});

test('an enumeration offers the robot its own choices', () => {
  const state = PlanState.empty(catalog(), 'lab', 'Stretch');
  const gripper = fieldOf(state, 'SetGripperAction', 'gripper');
  const motion = fieldOf(state, 'SetGripperAction', 'motion');
  assert.deepEqual(state.choices(state.activeRobot(), gripper), model(state, 'Stretch')[RobotModelKey.CHOICES].Arms);
  assert.deepEqual(state.choices(state.activeRobot(), motion), motion[ActionFieldKey.MEMBERS]);
});

// %% steps

test('a new step can run right away', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const arms = model(state, 'PR2')[RobotModelKey.CHOICES].Arms;
  state.addObject(objectModel(state, 1)[ObjectModelKey.IDENTIFIER]);
  const steps = ['ParkArmsAction', 'MoveTorsoAction', 'PickUpAction', 'PlaceAction', 'SetGripperAction'].map((action) => state.addStep(action));
  const [park, torso, pick, place, gripper] = steps.map((identifier) => values(state, identifier));
  assert.equal(park.arm, arms[0]);
  assert.equal(torso.torso_state, model(state, 'PR2')[RobotModelKey.CHOICES].TorsoState[0]);
  assert.equal(pick.object_designator, state.objects()[0][PlannedObjectKey.IDENTIFIER]);
  assert.equal(pick.grasp_description, undefined);
  assert.equal(place.target_location[DestinationKey.PLACEMENT], PlacementMode.POSE);
  assert.ok(PlanPose.isPose(place.target_location[DestinationKey.POSE]));
  assert.deepEqual(Object.keys(gripper), ['gripper', 'motion']);
  for (const identifier of steps) assert.deepEqual(state.problems(state.step(identifier)), []);
});

test('a pose target goes ahead of the robot, the next one beyond the last', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  state.setRobotPose(state.activeRobot()[PlannedRobotKey.IDENTIFIER], PlanPose.of(1, 2, 0, Math.PI / 2));
  const first = values(state, state.addStep('NavigateAction')).target_location;
  const second = values(state, state.addStep('NavigateAction')).target_location;
  const [x, y] = PlanPose.position(first);
  assert.ok(Math.abs(x - 1) < 1e-9 && y > 2);
  assert.ok(Math.abs(PlanPose.yaw(first) - Math.PI / 2) < 1e-9);
  assert.ok(PlanPose.position(second)[0] > x);
});

test('a plan full of steps refuses another', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const limit = state.limits[PlanBuilderLimitsKey.MAXIMUM_STEPS];
  for (let index = 0; index < limit; index += 1) state.addStep('ParkArmsAction');
  assert.throws(() => state.addStep('ParkArmsAction'), PlanRefused);
});

test('steps are inserted, moved and removed', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const park = state.addStep('ParkArmsAction');
  const torso = state.addStep('MoveTorsoAction', 0);
  const names = () => state.steps().map((step) => step[PlanStepKey.ACTION]);
  assert.deepEqual(names(), ['MoveTorsoAction', 'ParkArmsAction']);
  state.moveStep(torso, 1);
  assert.deepEqual(names(), ['ParkArmsAction', 'MoveTorsoAction']);
  state.moveStep(torso, 1);
  assert.deepEqual(names(), ['ParkArmsAction', 'MoveTorsoAction']);
  state.removeStep(park);
  assert.deepEqual(names(), ['MoveTorsoAction']);
});

test('a value is set and left to the default', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const park = state.addStep('ParkArmsAction');
  state.setValue(park, 'max_joint_velocity', 0.5);
  assert.equal(values(state, park).max_joint_velocity, 0.5);
  state.setValue(park, 'max_joint_velocity', null);
  assert.equal('max_joint_velocity' in values(state, park), false);
});

test('putting an object on a surface names a surface type, back at a pose a pose', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  state.addObject(objectModel(state, 1)[ObjectModelKey.IDENTIFIER]);
  const transport = state.addStep('TransportAction');
  state.setPlacement(transport, 'target_location', PlacementMode.SURFACE);
  const destination = values(state, transport).target_location;
  assert.equal(destination[DestinationKey.SURFACE_TYPE], state.catalog[PlanBuilderCatalogKey.SURFACE_TYPES][0]);
  state.setValue(transport, 'target_location', { [DestinationKey.PLACEMENT]: PlacementMode.SURFACE, [DestinationKey.SURFACE_TYPE]: 'Table' });
  state.setPlacement(transport, 'target_location', PlacementMode.POSE);
  assert.ok(PlanPose.isPose(values(state, transport).target_location[DestinationKey.POSE]));
});

test('a step names its pose targets, a put-down one with its object', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const milk = state.addObject(objectModel(state, 1)[ObjectModelKey.IDENTIFIER]);
  const look = state.step(state.addStep('LookAtAction'));
  const place = state.addStep('PlaceAction');
  assert.deepEqual(state.targets(look).map((target) => [target.field, target.object]), [['target', undefined]]);
  assert.deepEqual(state.targets(state.step(place)).map((target) => [target.field, target.object]), [['target_location', milk]]);
  const pose = PlanPose.of(1, 1, 1, 0);
  state.setTarget(place, 'target_location', pose);
  assert.deepEqual(values(state, place).target_location, { [DestinationKey.PLACEMENT]: PlacementMode.POSE, [DestinationKey.POSE]: pose });
  state.setTarget(look[PlanStepKey.IDENTIFIER], 'target', pose);
  assert.deepEqual(look[PlanStepKey.VALUES].target, pose);
  state.setPlacement(place, 'target_location', PlacementMode.SURFACE);
  assert.deepEqual(state.targets(state.step(place)), []);
});

test('a step that no longer fits its action names each problem', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const gripper = state.addStep('SetGripperAction');
  state.setValue(gripper, 'motion', 'SQUEEZE');
  state.setValue(gripper, 'speed', 2);
  state.setValue(gripper, 'gripper', null);
  const problems = state.problems(state.step(gripper));
  assert.equal(problems.length, 3);
  assert.match(problems.join(' '), /speed/);
  assert.match(problems.join(' '), /SQUEEZE/);
  assert.match(problems.join(' '), /gripper/);
  const gone = new PlanState(catalog(), { [PlanKey.NAME]: 'x', [PlanKey.ROBOTS]: [{ ...state.activeRobot(), [PlannedRobotKey.STEPS]: [{ [PlanStepKey.IDENTIFIER]: 'step_1', [PlanStepKey.ACTION]: 'SearchAction' }] }] });
  assert.match(gone.problems(gone.steps()[0])[0], /SearchAction/);
  const unavailable = state.addStep('ParkArmsAction');
  state.step(unavailable)[PlanStepKey.ACTION] = 'FollowToolCenterPointPathAction';
  assert.match(state.problems(state.step(unavailable))[0], /PoseTrajectory/);
});

test('values of the wrong type are problems', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  state.addObject(objectModel(state, 1)[ObjectModelKey.IDENTIFIER]);
  const pick = state.addStep('PickUpAction');
  for (const [name, value] of [['object_designator', 'bowl'], ['tolerate_grasp_stall', 'yes'], ['grasp_description', 'top'], ['object_friction', 'much']]) {
    const original = values(state, pick)[name] ?? null;
    state.setValue(pick, name, value);
    assert.equal(state.problems(state.step(pick)).length, 1, name);
    state.setValue(pick, name, original);
  }
  const look = state.addStep('LookAtAction');
  state.setValue(look, 'target', [1, 2]);
  assert.equal(state.problems(state.step(look)).length, 1);
  const transport = state.addStep('TransportAction');
  state.setValue(transport, 'target_location', { [DestinationKey.PLACEMENT]: PlacementMode.SURFACE });
  assert.equal(state.problems(state.step(transport)).length, 1);
});

test('a step holds each constraint once and within the limit', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const park = state.addStep('ParkArmsAction');
  const constraint = (text) => ({ [StepConstraintKey.TEXT]: text });
  assert.equal(state.attachConstraint(park, constraint('one')), true);
  assert.equal(state.attachConstraint(park, constraint('one')), false);
  state.attachConstraint(park, constraint('two'));
  assert.throws(() => state.attachConstraint(park, constraint('three')), PlanRefused);
  state.detachConstraint(park, 0);
  assert.deepEqual(state.step(park)[PlanStepKey.CONSTRAINTS], [constraint('two')]);
});

// %% robots

test('changing the model keeps the actions it offers with its choices and takes its name', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const identifier = state.activeRobot()[PlannedRobotKey.IDENTIFIER];
  state.addStep('MoveTorsoAction');
  const park = state.addStep('ParkArmsAction');
  state.setValue(park, 'arm', 'RIGHT');
  assert.equal(state.setRobotModel(identifier, 'Stretch'), 0);
  assert.equal(values(state, park).arm, model(state, 'Stretch')[RobotModelKey.CHOICES].Arms[0]);
  assert.equal(state.setRobotModel(identifier, 'Tracy'), 1);
  assert.equal(state.activeRobot()[PlannedRobotKey.LABEL], 'Tracy 1');
});

test('the last robot is kept', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const first = state.activeRobot()[PlannedRobotKey.IDENTIFIER];
  const second = state.addRobot('PR2');
  assert.equal(state.activeRobot()[PlannedRobotKey.LABEL], 'PR2 2');
  assert.equal(state.removeRobot(second), true);
  assert.equal(state.activeRobot()[PlannedRobotKey.IDENTIFIER], first);
  assert.equal(state.removeRobot(first), false);
});

test('a plan full of robots refuses another', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  while (state.robots().length < state.limits[PlanBuilderLimitsKey.MAXIMUM_ROBOTS]) state.addRobot('PR2');
  assert.throws(() => state.addRobot('PR2'), PlanRefused);
  assert.throws(() => state.addRobot('R2D2'), PlanRefused);
});

// %% objects

test('an object is named after its model as an identity and once', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const [knife, milk, cup] = state.catalog[PlanBuilderCatalogKey.OBJECTS].map((entry) => entry[ObjectModelKey.IDENTIFIER]);
  assert.equal(state.addObject(knife), 'big_knife');
  assert.equal(state.addObject(milk), 'milk');
  assert.equal(state.addObject(milk), 'milk_1');
  assert.equal(state.addObject(cup), `${IdentityPrefix.OBJECT}3d_cup`);
  assert.throws(() => state.addObject('anvil.stl'), PlanRefused);
});

test('removing an object moves its steps to the next object, or leaves them without', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const milk = state.addObject(objectModel(state, 1)[ObjectModelKey.IDENTIFIER]);
  const knife = state.addObject(objectModel(state, 0)[ObjectModelKey.IDENTIFIER]);
  const pick = state.addStep('PickUpAction');
  state.removeObject(milk);
  assert.equal(values(state, pick).object_designator, knife);
  assert.equal(state.stepObject(state.step(pick)), knife);
  state.removeObject(knife);
  assert.equal(values(state, pick).object_designator, undefined);
});

test('an object takes a pose and a colour', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const milk = state.addObject(objectModel(state, 1)[ObjectModelKey.IDENTIFIER]);
  state.setObjectPose(milk, PlanPose.of(1, 2, 3, 0));
  state.setObjectColor(milk, '#ff0000');
  assert.deepEqual(PlanPose.position(state.object(milk)[PlannedObjectKey.POSE]), [1, 2, 3]);
  assert.equal(state.object(milk)[PlannedObjectKey.COLOR], '#ff0000');
  state.setObjectColor(milk, null);
  assert.equal(state.object(milk)[PlannedObjectKey.COLOR], undefined);
});

test('fields are set and left out', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  state.setField(PlanKey.TASK, 'Carry the milk');
  assert.equal(state.document[PlanKey.TASK], 'Carry the milk');
  state.setField(PlanKey.ENVIRONMENT, null);
  assert.equal(PlanKey.ENVIRONMENT in state.document, false);
});

test('a saved plan is edited as it was saved', () => {
  const saved = PlanState.empty(catalog(), 'lab', 'Tracy');
  saved.addStep('ParkArmsAction');
  const reopened = new PlanState(catalog(), saved.document);
  assert.deepEqual(reopened.document, saved.document);
  assert.throws(() => reopened.robot('robot_9'), PlanRefused);
  assert.throws(() => reopened.step('step_9'), PlanRefused);
  assert.throws(() => reopened.object('milk'), PlanRefused);
});
