import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
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
  StepKind,
} from 'cramera-viewer/protocol.js';
import { IdentityPrefix, NEW_PLAN_NAME, PlanRefused, PlanState } from '../../src/cramera_plan_builder/web/builder/plan-state.js';
import { PlanPose } from '../../src/cramera_plan_builder/web/builder/poses.js';

const catalog = () => JSON.parse(readFileSync(new URL('dataset/catalog.json', import.meta.url), 'utf8'));
const model = (state, name) => state.catalog[PlanBuilderCatalogKey.ROBOTS].find((entry) => entry[RobotModelKey.NAME] === name);
const objectModel = (state, index) => state.catalog[PlanBuilderCatalogKey.OBJECTS][index];

// %% new plans

test('a new plan starts with one robot of the model offering the most steps', () => {
  const state = PlanState.empty(catalog(), 'lab');
  const robot = state.activeRobot();
  assert.equal(state.field(PlanKey.NAME), NEW_PLAN_NAME);
  assert.equal(state.field(PlanKey.ENVIRONMENT), 'lab');
  assert.equal(state.robots().length, 1);
  assert.deepEqual(state.offeredSteps(robot), Object.values(StepKind));
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

// %% steps

test('a new step can run right away', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const arms = model(state, 'PR2')[RobotModelKey.ARMS];
  state.addObject(objectModel(state, 1)[ObjectModelKey.IDENTIFIER]);
  const park = state.step(state.addStep(StepKind.PARK_ARMS));
  const torso = state.step(state.addStep(StepKind.MOVE_TORSO));
  const pick = state.step(state.addStep(StepKind.PICK_UP));
  const place = state.step(state.addStep(StepKind.PLACE));
  assert.equal(park[PlanStepKey.ARM], arms[arms.length - 1]);
  assert.equal(torso[PlanStepKey.TORSO_STATE], state.catalog[PlanBuilderCatalogKey.TORSO_STATES][0]);
  assert.equal(pick[PlanStepKey.ARM], arms[0]);
  assert.equal(pick[PlanStepKey.OBJECT], state.objects()[0][PlannedObjectKey.IDENTIFIER]);
  assert.equal(place[PlanStepKey.PLACEMENT], PlacementMode.POSE);
  assert.ok(PlanPose.isPose(place[PlanStepKey.TARGET]));
});

test('a navigation goes ahead of the robot, the next one beyond the last', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  state.setRobotPose(state.activeRobot()[PlannedRobotKey.IDENTIFIER], PlanPose.of(1, 2, 0, Math.PI / 2));
  const first = state.step(state.addStep(StepKind.NAVIGATE));
  const second = state.step(state.addStep(StepKind.NAVIGATE));
  const [x, y] = PlanPose.position(first[PlanStepKey.TARGET]);
  assert.ok(Math.abs(x - 1) < 1e-9 && y > 2);
  assert.ok(Math.abs(PlanPose.yaw(first[PlanStepKey.TARGET]) - Math.PI / 2) < 1e-9);
  assert.ok(PlanPose.position(second[PlanStepKey.TARGET])[0] > x);
});

test('a step the robot cannot take is refused', () => {
  const state = PlanState.empty(catalog(), 'lab', 'Tracy');
  assert.throws(() => state.addStep(StepKind.NAVIGATE), PlanRefused);
});

test('a plan full of steps refuses another', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const limit = state.limits[PlanBuilderLimitsKey.MAXIMUM_STEPS];
  for (let index = 0; index < limit; index += 1) state.addStep(StepKind.PARK_ARMS);
  assert.throws(() => state.addStep(StepKind.PARK_ARMS), PlanRefused);
});

test('steps are inserted, moved and removed', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const park = state.addStep(StepKind.PARK_ARMS);
  const torso = state.addStep(StepKind.MOVE_TORSO, 0);
  const kinds = () => state.steps().map((step) => step[PlanStepKey.KIND]);
  assert.deepEqual(kinds(), [StepKind.MOVE_TORSO, StepKind.PARK_ARMS]);
  state.moveStep(torso, 1);
  assert.deepEqual(kinds(), [StepKind.PARK_ARMS, StepKind.MOVE_TORSO]);
  state.moveStep(torso, 1);
  assert.deepEqual(kinds(), [StepKind.PARK_ARMS, StepKind.MOVE_TORSO]);
  state.removeStep(park);
  assert.deepEqual(kinds(), [StepKind.MOVE_TORSO]);
});

test('putting an object on a surface names a surface type, back at a pose a pose', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  state.addObject(objectModel(state, 1)[ObjectModelKey.IDENTIFIER]);
  const transport = state.addStep(StepKind.TRANSPORT);
  state.updateStep(transport, { [PlanStepKey.PLACEMENT]: PlacementMode.SURFACE, [PlanStepKey.TARGET]: null });
  assert.equal(state.step(transport)[PlanStepKey.SURFACE_TYPE], state.catalog[PlanBuilderCatalogKey.SURFACE_TYPES][0]);
  assert.equal(state.step(transport)[PlanStepKey.TARGET], undefined);
  state.updateStep(transport, { [PlanStepKey.PLACEMENT]: PlacementMode.POSE });
  assert.ok(PlanPose.isPose(state.step(transport)[PlanStepKey.TARGET]));
});

test('a step holds each constraint once and within the limit', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const park = state.addStep(StepKind.PARK_ARMS);
  const constraint = (text) => ({ [StepConstraintKey.TEXT]: text });
  assert.equal(state.attachConstraint(park, constraint('one')), true);
  assert.equal(state.attachConstraint(park, constraint('one')), false);
  state.attachConstraint(park, constraint('two'));
  assert.throws(() => state.attachConstraint(park, constraint('three')), PlanRefused);
  state.detachConstraint(park, 0);
  assert.deepEqual(state.step(park)[PlanStepKey.CONSTRAINTS], [constraint('two')]);
});

// %% robots

test('changing the model keeps the steps it offers and takes its name', () => {
  const state = PlanState.empty(catalog(), 'lab', 'PR2');
  const identifier = state.activeRobot()[PlannedRobotKey.IDENTIFIER];
  state.addStep(StepKind.NAVIGATE);
  const pick = state.addStep(StepKind.PICK_UP);
  state.updateStep(pick, { [PlanStepKey.ARM]: 'RIGHT' });
  assert.equal(state.setRobotModel(identifier, 'Stretch'), 0);
  assert.equal(state.step(pick)[PlanStepKey.ARM], model(state, 'Stretch')[RobotModelKey.ARMS][0]);
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
  const pick = state.addStep(StepKind.PICK_UP);
  state.removeObject(milk);
  assert.equal(state.step(pick)[PlanStepKey.OBJECT], knife);
  state.removeObject(knife);
  assert.equal(state.step(pick)[PlanStepKey.OBJECT], undefined);
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
  saved.addStep(StepKind.PARK_ARMS);
  const reopened = new PlanState(catalog(), saved.document);
  assert.deepEqual(reopened.document, saved.document);
  assert.throws(() => reopened.robot('robot_9'), PlanRefused);
  assert.throws(() => reopened.step('step_9'), PlanRefused);
  assert.throws(() => reopened.object('milk'), PlanRefused);
});
