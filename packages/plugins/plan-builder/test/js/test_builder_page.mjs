import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  ActionCatalogKey,
  ActionSchemaKey,
  ConstraintRequestKey,
  ConstraintRuleKey,
  ConstraintTextKey,
  DemoSourceKey,
  PageState,
  DestinationKey,
  PlacementMode,
  PageStateAttribute,
  PlanBuilderCatalogKey,
  PlanBuilderPageParameter,
  PlanKey,
  PlannedObjectKey,
  PlannedRobotKey,
  PlanRecordKey,
  PlanStepKey,
  RunMode,
  RunState,
  RunStatusKey,
  SavedDemoKey,
  StepConstraintKey,
  ViewerEvent,
} from 'cramera-viewer/protocol.js';
import { EventBus } from 'cramera-viewer/core/event-bus.js';
import { PanelHost } from 'cramera-viewer/panels/panel-host.js';
import { BuilderEnvironment, BuilderPage, ROBOT_MODEL_KEY } from '../../src/cramera_plan_builder/web/builder/builder-page.js';
import { SENTENCES_KEY } from '../../src/cramera_plan_builder/web/builder/constraints-view.js';
import { DRAG_MEDIA_TYPE, DragKind, DragText, DomEvent, PlanAction } from '../../src/cramera_plan_builder/web/builder/elements.js';
import { MarkerKind, Selection, TransformMode } from '../../src/cramera_plan_builder/web/builder/plan-scene.js';
import { PlanPose } from '../../src/cramera_plan_builder/web/builder/poses.js';
import { EnvironmentNote } from '../../src/cramera_plan_builder/web/builder/robots-view.js';
import { STEP_PALETTE_SIZE } from '../../src/cramera_plan_builder/web/builder/steps-view.js';
import { PANEL_TITLE, register } from '../../src/cramera_plan_builder/web/index.js';
import { FakeDocument, FakeStorage } from 'cramera-testing/fake-document.mjs';

const read = (name) => JSON.parse(readFileSync(new URL(name, import.meta.url), 'utf8'));
const RULES = read('../../src/cramera_plan_builder/rules/constraints.json').rules;
const ACTIONS = read('../dataset/actions.json');
const byAction = (root, action) => root.findAll((element) => element.dataset.action === action);
const settled = () => new Promise((resolve) => setImmediate(resolve));
const drop = (element, text) => element.dispatch(DomEvent.DROP, { dataTransfer: { getData: (type) => (type === DRAG_MEDIA_TYPE ? text : '') } });

/**
 * Answers the page's requests and records what it asked.
 */
class FakeApi {
  constructor() {
    this.catalogAnswer = {
      ...read('dataset/catalog.json'),
      [PlanBuilderCatalogKey.CONSTRAINT_RULES]: RULES,
      [PlanBuilderCatalogKey.ACTIONS]: ACTIONS[ActionCatalogKey.ACTIONS],
      [PlanBuilderCatalogKey.FAILED_ACTION_MODULES]: ACTIONS[ActionCatalogKey.FAILED_MODULES],
    };
    this.saved = [];
    this.compiled = [];
    this.runs = [];
    this.status = { [RunStatusKey.STATE]: RunState.IDLE };
    this.stopped = 0;
  }

  async catalog() {
    return structuredClone(this.catalogAnswer);
  }

  async plans() {
    return { [PlanBuilderCatalogKey.PLANS]: this.saved.map((record) => ({ id: record[PlanRecordKey.IDENTIFIER], name: record[PlanRecordKey.DOCUMENT][PlanKey.NAME] })) };
  }

  async plan(identifier) {
    const found = this.saved.find((record) => record[PlanRecordKey.IDENTIFIER] === identifier);
    if (!found) throw new Error(`No saved plan is named ${identifier}.`);
    return structuredClone(found);
  }

  async save(plan, identifier) {
    const record = { [PlanRecordKey.IDENTIFIER]: identifier ?? `plan-${this.saved.length + 1}`, [PlanRecordKey.DOCUMENT]: plan };
    this.saved.push(record);
    return structuredClone(record);
  }

  async compile(request) {
    this.compiled.push(request);
    const text = request[ConstraintTextKey.TEXT];
    const rule = RULES.find((candidate) => new RegExp(candidate[ConstraintRuleKey.PHRASING]).test(text.toLowerCase()));
    const compiled = { [StepConstraintKey.TEXT]: text };
    if (rule) compiled[StepConstraintKey.MONITOR_TYPE] = rule[ConstraintRuleKey.MONITOR_TYPE];
    if (rule && request[ConstraintTextKey.STEP_ACTION]) compiled[StepConstraintKey.MONITOR] = { type: rule[ConstraintRuleKey.MONITOR_TYPE], params: {} };
    return compiled;
  }

  async demo(plan) {
    return { [DemoSourceKey.FILE_NAME]: `${plan[PlanKey.NAME]}.py`, [DemoSourceKey.SOURCE]: `DEMO = ${JSON.stringify(plan)}` };
  }

  async writeDemo(plan) {
    return { [SavedDemoKey.PATH]: `/demos/${plan[PlanKey.NAME]}.py`, [SavedDemoKey.COMMAND]: `python /demos/${plan[PlanKey.NAME]}.py` };
  }

  async run(plan, mode) {
    this.runs.push({ plan, mode });
    this.status = { [RunStatusKey.STATE]: RunState.RUNNING, [RunStatusKey.MODE]: mode, [RunStatusKey.LOG]: 'building the world' };
    return structuredClone(this.status);
  }

  async runStatus() {
    return structuredClone(this.status);
  }

  async stop() {
    this.stopped += 1;
    this.status = { ...this.status, [RunStatusKey.STATE]: RunState.STOPPED };
    return structuredClone(this.status);
  }

  objectUrl(identifier) {
    return `objects/${identifier}`;
  }
}

/**
 * A live publisher answering from the test world, recording moves and constraints.
 */
class FakeLive {
  constructor() {
    this.world = read('dataset/live_world.json');
    this.planAnswer = read('dataset/live_plan.json');
    this.moves = [];
    this.attached = [];
  }

  async info() {
    return this.world.info;
  }

  async objects() {
    return this.world.objects;
  }

  async capturedObjects() {
    return this.world.captured;
  }

  async robots() {
    return this.world.robots;
  }

  async plan() {
    return this.planAnswer;
  }

  async surfaces() {
    return this.world.surfaces;
  }

  async move(key, pose, final) {
    this.moves.push({ key, pose, final });
    return {};
  }

  async attach(request) {
    this.attached.push(request);
    return {};
  }
}

/**
 * A 3D view that records what the page shows.
 */
class FakeScene {
  constructor(listeners) {
    this.listeners = listeners;
    this.environments = [];
    this.shown = null;
    this.selected = null;
    this.mode = TransformMode.MOVE;
    this.framed = 0;
    this.disposed = false;
  }

  async showEnvironment(name) {
    this.environments.push(name);
  }

  show(state, live) {
    this.shown = { document: state.document, live };
  }

  select(selection) {
    this.selected = selection;
  }

  setMode(mode) {
    this.mode = mode;
  }

  frame() {}

  frameMarkers() {
    this.framed += 1;
  }

  dispose() {
    this.disposed = true;
  }
}

/**
 * A timer the test triggers by hand.
 */
class FakeTimer {
  constructor() {
    this.callbacks = new Map();
    this.next = 1;
  }

  repeat(callback) {
    const handle = this.next++;
    this.callbacks.set(handle, callback);
    return handle;
  }

  cancel(handle) {
    this.callbacks.delete(handle);
  }

  async tick() {
    for (const callback of [...this.callbacks.values()]) await callback();
    await settled();
  }
}

async function openPage(query = '', prepare = () => {}) {
  const document = new FakeDocument();
  const api = new FakeApi();
  const live = new FakeLive();
  const timer = new FakeTimer();
  const storage = new FakeStorage();
  prepare({ api, storage });
  let scene = null;
  const environment = new BuilderEnvironment({
    document,
    api,
    live: () => live,
    storage,
    query: new URLSearchParams(query),
    createScene: (container, listeners) => (scene = new FakeScene(listeners)),
    timer,
  });
  const root = document.createElement('div');
  document.body.append(root);
  const page = new BuilderPage(root, environment);
  await page.start();
  await settled();
  return { document, api, live, timer, storage, root, page, scene: () => scene };
}

const message = (root) => root.findAll((element) => element.className === 'message')[0].textContent;
const block = (root, action) => root.findAll((element) => element.dataset.action === PlanAction.ADD_STEP && element.dataset.name === action)[0];
const parameter = (root, field) => byAction(root, PlanAction.STEP_PARAMETER).find((element) => element.dataset.field === field);
const steps = (root) => root.findAll((element) => element.dataset.step !== undefined);

/**
 * Add a copy of the milk, the object the test's live world holds.
 * @param {Object} root The page's root.
 */
function addMilk(root) {
  const model = byAction(root, PlanAction.OBJECT_MODEL)[0];
  model.value = 'milk.stl';
  model.dispatch(DomEvent.CHANGE);
  byAction(root, PlanAction.ADD_OBJECT)[0].click();
}

// %% starting

test('the page starts a plan in the first environment and is ready', async () => {
  const { document, root, page, api, scene, timer } = await openPage();
  assert.equal(document.documentElement.dataset[PageStateAttribute.STATE], PageState.READY);
  assert.equal(page.state.field(PlanKey.ENVIRONMENT), api.catalogAnswer[PlanBuilderCatalogKey.ENVIRONMENTS][0].name);
  assert.deepEqual(scene().environments, [page.state.field(PlanKey.ENVIRONMENT)]);
  assert.equal(byAction(root, PlanAction.ADD_STEP).length, page.state.offeredActions(page.state.activeRobot()).length);
  assert.equal(timer.callbacks.size, 1);
});

test('the page starts in the environment its query names, with the last robot model', async () => {
  const { page } = await openPage(`${PlanBuilderPageParameter.ENVIRONMENT}=nowhere`, ({ storage }) => storage.setItem(ROBOT_MODEL_KEY, 'tracy'));
  assert.equal(page.state.activeRobot()[PlannedRobotKey.MODEL], 'tracy');
  assert.equal(page.state.field(PlanKey.ENVIRONMENT), 'lab');
});

test('the page opens the saved plan its query names', async () => {
  const { page } = await openPage(`${PlanBuilderPageParameter.PLAN}=plan-1`, ({ api }) => {
    api.saved.push({ [PlanRecordKey.IDENTIFIER]: 'plan-1', [PlanRecordKey.DOCUMENT]: { [PlanKey.NAME]: 'opened', [PlanKey.ROBOTS]: [] } });
  });
  assert.equal(page.state.field(PlanKey.NAME), 'opened');
});

test('without the CRAM workspace the page composes but does not run', async () => {
  const { document, root } = await openPage('', ({ api }) => {
    api.catalogAnswer[PlanBuilderCatalogKey.MISSING] = ['coraplex'];
  });
  assert.match(document.documentElement.dataset[PageStateAttribute.STATUS], /coraplex/);
  assert.equal(byAction(root, PlanAction.STAGE)[0].disabled, true);
  assert.equal(byAction(root, PlanAction.PERFORM)[0].disabled, true);
});

// %% composing

test('clicking an action and dropping one add steps where they land', async () => {
  const { root, page } = await openPage();
  block(root, 'park_arms').click();
  drop(steps(root)[0], DragText.of(DragKind.STEP, 'move_torso'));
  assert.deepEqual(page.state.steps().map((step) => step[PlanStepKey.ACTION]), ['move_torso', 'park_arms']);
  assert.equal(steps(root)[0].findAll((element) => element.className === 'step-name')[0].textContent, page.state.schema('move_torso')[ActionSchemaKey.LABEL]);
  assert.ok(Number(steps(root)[0].dataset.palette) < STEP_PALETTE_SIZE);
});

test('the palette groups the actions and names why others are not available', async () => {
  const { root, page } = await openPage('', ({ storage }) => storage.setItem(ROBOT_MODEL_KEY, 'tracy'));
  const groups = root.findAll((element) => element.className === 'palette-group').map((element) => element.dataset.group);
  assert.deepEqual(groups, [...new Set(page.state.offeredActions(page.state.activeRobot()).map((schema) => schema[ActionSchemaKey.GROUP]))]);
  const refused = root.findAll((element) => element.className === 'block unavailable');
  const reasons = new Map(refused.map((element) => [element.dataset.name, element.children[1].textContent]));
  const unavailable = ACTIONS[ActionCatalogKey.ACTIONS].find((schema) => !schema[ActionSchemaKey.AVAILABLE]);
  assert.equal(reasons.get(unavailable[ActionSchemaKey.NAME]), unavailable[ActionSchemaKey.UNAVAILABLE_REASON]);
  assert.match(reasons.get('move_torso'), /TorsoState/);
  const notice = root.findAll((element) => element.className === 'notice')[0];
  assert.match(notice.textContent, new RegExp(ACTIONS[ActionCatalogKey.FAILED_MODULES][0].module));
});

test('a gripper step offers its enumerations with the choices of the robot', async () => {
  const { root, page } = await openPage('', ({ storage }) => storage.setItem(ROBOT_MODEL_KEY, 'stretch'));
  block(root, 'set_gripper').click();
  const gripper = parameter(root, 'gripper');
  const motion = parameter(root, 'motion');
  assert.deepEqual(gripper.children.map((option) => option.value), ['BOTH']);
  assert.deepEqual(motion.children.map((option) => option.value), ['OPEN', 'CLOSE', 'MEDIUM']);
  motion.value = 'CLOSE';
  motion.dispatch(DomEvent.CHANGE);
  assert.equal(page.state.steps()[0][PlanStepKey.VALUES].motion, 'CLOSE');
  assert.equal(root.findAll((element) => element.className === 'more-options').length, 0);
});

test('optional fields fold under more options and keep their defaults until set', async () => {
  const { root, page } = await openPage();
  byAction(root, PlanAction.ADD_OBJECT)[0].click();
  block(root, 'pick_up').click();
  const values = () => page.state.steps()[0][PlanStepKey.VALUES];
  assert.equal(root.findAll((element) => element.className === 'more-options').length, 1);
  assert.match(root.findAll((element) => element.className === 'derived')[0].textContent, /derived from arm and object_designator/);
  const stall = parameter(root, 'tolerate_grasp_stall');
  stall.checked = true;
  stall.dispatch(DomEvent.CHANGE);
  assert.equal(values().tolerate_grasp_stall, true);
  const friction = parameter(root, 'object_friction');
  assert.equal(friction.placeholder, 'default');
  friction.value = '0.4';
  friction.dispatch(DomEvent.CHANGE);
  assert.equal(values().object_friction, 0.4);
  const cleared = parameter(root, 'object_friction');
  cleared.value = '';
  cleared.dispatch(DomEvent.CHANGE);
  assert.equal('object_friction' in values(), false);
});

test('an annotation without a live entity is typed by name', async () => {
  const { root, page } = await openPage();
  byAction(root, PlanAction.ADD_OBJECT)[0].click();
  block(root, 'cutting').click();
  const tool = parameter(root, 'tool');
  assert.match(root.findAll((element) => element.className === 'empty').map((element) => element.textContent).join(' '), /Tool annotation/);
  tool.value = 'knife';
  tool.dispatch(DomEvent.CHANGE);
  assert.equal(page.state.steps()[0][PlanStepKey.VALUES].tool, 'knife');
  const stride = parameter(root, 'pointer_stride');
  stride.value = '2.6';
  stride.dispatch(DomEvent.CHANGE);
  assert.equal(page.state.steps()[0][PlanStepKey.VALUES].pointer_stride, 3);
});

test('a step that no longer fits its action shows why', async () => {
  const { page, root } = await openPage(`${PlanBuilderPageParameter.PLAN}=plan-1`, ({ api }) => {
    api.saved.push({
      [PlanRecordKey.IDENTIFIER]: 'plan-1',
      [PlanRecordKey.DOCUMENT]: {
        [PlanKey.NAME]: 'stale',
        [PlanKey.ROBOTS]: [{ id: 'robot_1', model: 'pr2', label: 'PR2 1', pose: [0, 0, 0, 0, 0, 0, 1], steps: [{ id: 'step_1', action: 'search', values: {} }] }],
      },
    });
  });
  const problems = root.findAll((element) => element.className === 'step-problem').map((element) => element.textContent);
  assert.deepEqual(problems, page.state.problems(page.state.steps()[0]));
  assert.equal(steps(root)[0].findAll((element) => element.className === 'step-name')[0].textContent, 'search');
});

test('a step is moved and removed with its controls', async () => {
  const { root, page } = await openPage();
  block(root, 'park_arms').click();
  block(root, 'move_torso').click();
  byAction(root, PlanAction.MOVE_STEP_DOWN)[0].click();
  assert.equal(page.state.steps()[0][PlanStepKey.ACTION], 'move_torso');
  byAction(root, PlanAction.REMOVE_STEP)[0].click();
  assert.deepEqual(page.state.steps().map((step) => step[PlanStepKey.ACTION]), ['park_arms']);
});

test('a refused edit is reported', async () => {
  const { root, page } = await openPage();
  for (let count = 0; count <= page.state.limits.maximumSteps; count += 1) block(root, 'park_arms').click();
  assert.match(message(root), /At most/);
});

test('a dropped sentence is compiled for its step and attached', async () => {
  const { root, page, api } = await openPage();
  byAction(root, PlanAction.ADD_OBJECT)[0].click();
  block(root, 'pick_up').click();
  drop(steps(root)[0], DragText.of(DragKind.CONSTRAINT, RULES[0][ConstraintRuleKey.SENTENCE]));
  await settled();
  const [request] = api.compiled;
  assert.equal(request[ConstraintTextKey.STEP_ACTION], 'pick_up');
  assert.equal(request[ConstraintTextKey.STEP_OBJECT], page.state.objects()[0][PlannedObjectKey.IDENTIFIER]);
  assert.equal(page.state.steps()[0][PlanStepKey.CONSTRAINTS][0][StepConstraintKey.MONITOR_TYPE], RULES[0][ConstraintRuleKey.MONITOR_TYPE]);
  assert.equal(root.findAll((element) => element.className === 'chip').length, 1);
});

test('a sentence no rule reads is not attached', async () => {
  const { root, page } = await openPage();
  block(root, 'park_arms').click();
  drop(steps(root)[0], DragText.of(DragKind.CONSTRAINT, 'Sing while working'));
  await settled();
  assert.deepEqual(page.state.steps()[0][PlanStepKey.CONSTRAINTS], []);
  assert.match(message(root), /No rule/);
});

test('a written sentence joins the palette and the browser keeps it', async () => {
  const { root, storage } = await openPage();
  const input = byAction(root, PlanAction.CONSTRAINT_TEXT)[0];
  input.value = 'Keep the cup level';
  byAction(root, PlanAction.ADD_CONSTRAINT)[0].click();
  await settled();
  assert.deepEqual(JSON.parse(storage.getItem(SENTENCES_KEY)).map((sentence) => sentence[StepConstraintKey.TEXT]), ['Keep the cup level']);
  assert.equal(byAction(root, PlanAction.REMOVE_CONSTRAINT).length, 1);
  byAction(root, PlanAction.REMOVE_CONSTRAINT)[0].click();
  assert.deepEqual(JSON.parse(storage.getItem(SENTENCES_KEY)), []);
});

test('robots are added, edited and removed', async () => {
  const { root, page } = await openPage();
  byAction(root, PlanAction.ADD_ROBOT)[0].click();
  assert.equal(page.state.robots().length, 2);
  const label = byAction(root, PlanAction.ROBOT_LABEL)[0];
  label.value = 'Helper';
  label.dispatch(DomEvent.CHANGE);
  assert.equal(page.state.activeRobot()[PlannedRobotKey.LABEL], 'Helper');
  const x = byAction(root, PlanAction.POSE).find((input) => input.dataset.field === 'x');
  x.value = '2.5';
  x.dispatch(DomEvent.CHANGE);
  assert.equal(PlanPose.position(page.state.activeRobot()[PlannedRobotKey.POSE])[0], 2.5);
  byAction(root, PlanAction.REMOVE_ROBOT)[0].click();
  assert.equal(page.state.robots().length, 1);
});

test('the name is edited in the bar and the environment in its section', async () => {
  const { root, page, scene } = await openPage();
  const name = byAction(root, PlanAction.NAME)[0];
  name.value = 'milk_run';
  name.dispatch(DomEvent.CHANGE);
  const bar = root.findAll((element) => element.className === 'bar builder-bar')[0];
  assert.equal(bar.findAll((element) => element.dataset.action === PlanAction.ENVIRONMENT).length, 0);
  const environment = byAction(root, PlanAction.ENVIRONMENT)[0];
  environment.value = '';
  environment.dispatch(DomEvent.CHANGE);
  assert.equal(page.state.field(PlanKey.NAME), 'milk_run');
  assert.equal(page.state.field(PlanKey.ENVIRONMENT), '');
  assert.deepEqual(scene().environments.at(-1), null);
});

const environmentNote = (root) => root.findAll((element) => element.className === 'muted environment-note')[0].textContent;

test('the environment section says where the robots start', async () => {
  const { root } = await openPage();
  assert.equal(environmentNote(root), EnvironmentNote.chosen('Test laboratory'));
  const environment = byAction(root, PlanAction.ENVIRONMENT)[0];
  environment.value = '';
  environment.dispatch(DomEvent.CHANGE);
  assert.equal(environmentNote(root), EnvironmentNote.EMPTY_FLOOR);
});

test('without an environment on offer the section says where environments come from', async () => {
  const { root, page } = await openPage('', ({ api }) => {
    api.catalogAnswer[PlanBuilderCatalogKey.ENVIRONMENTS] = [];
  });
  assert.equal(page.state.field(PlanKey.ENVIRONMENT), '');
  assert.equal(environmentNote(root), EnvironmentNote.NONE_OFFERED);
});

const robotEntries = (root) => byAction(root, PlanAction.SELECT_ROBOT);

test('the robots are listed and the one whose plan is edited is marked', async () => {
  const { root, page } = await openPage();
  byAction(root, PlanAction.ADD_ROBOT)[0].click();
  const [first, second] = page.state.robots().map((robot) => robot[PlannedRobotKey.IDENTIFIER]);
  assert.deepEqual(robotEntries(root).map((entry) => entry.dataset.robot), [first, second]);
  const pressed = () => robotEntries(root).filter((entry) => entry.getAttribute('aria-pressed') === 'true').map((entry) => entry.dataset.robot);
  assert.deepEqual(pressed(), [page.state.activeRobot()[PlannedRobotKey.IDENTIFIER]]);
  robotEntries(root).find((entry) => entry.dataset.robot === first).click();
  assert.equal(page.state.activeRobot()[PlannedRobotKey.IDENTIFIER], first);
  assert.deepEqual(pressed(), [first]);
  assert.equal(root.findAll((element) => element.tagName === 'H2' && element.textContent.startsWith('Plan of'))[0].textContent, `Plan of ${page.state.activeRobot()[PlannedRobotKey.LABEL]}`);
});

test('a robot picked in the 3D view becomes the one whose plan is edited', async () => {
  const { root, page, scene } = await openPage();
  byAction(root, PlanAction.ADD_ROBOT)[0].click();
  const [first] = page.state.robots().map((robot) => robot[PlannedRobotKey.IDENTIFIER]);
  scene().listeners.onPick(new Selection(MarkerKind.ROBOT, first));
  assert.equal(page.state.activeRobot()[PlannedRobotKey.IDENTIFIER], first);
});

test('the last robot cannot be removed', async () => {
  const { root, page } = await openPage();
  assert.equal(page.state.robots().length, 1);
  assert.equal(byAction(root, PlanAction.REMOVE_ROBOT)[0].disabled, true);
});

// %% 3D view

test('a dragged object moves in the plan and, while live, in the live world', async () => {
  const { root, page, live, timer, api, scene } = await openPage();
  addMilk(root);
  byAction(root, PlanAction.STAGE)[0].click();
  await settled();
  await timer.tick();
  const milk = page.state.objects()[0][PlannedObjectKey.IDENTIFIER];
  const pose = PlanPose.of(2, 1, 0.9, 0);
  scene().listeners.onPlace(new Selection(MarkerKind.OBJECT, milk), pose);
  await settled();
  assert.deepEqual(page.state.object(milk)[PlannedObjectKey.POSE], pose);
  assert.deepEqual(live.moves, [{ key: 'key-milk', pose, final: true }]);
  assert.equal(api.runs[0].mode, RunMode.STAGE);
});

test('an object edited in the list moves in the live world too', async () => {
  const { root, page, live, timer } = await openPage();
  addMilk(root);
  byAction(root, PlanAction.STAGE)[0].click();
  await settled();
  await timer.tick();
  const entry = root.findAll((element) => element.dataset.object !== undefined)[0];
  const x = byAction(entry, PlanAction.POSE).find((input) => input.dataset.field === 'x');
  x.value = '3';
  x.dispatch(DomEvent.CHANGE);
  await settled();
  const pose = page.state.objects()[0][PlannedObjectKey.POSE];
  assert.equal(PlanPose.position(pose)[0], 3);
  assert.deepEqual(live.moves, [{ key: 'key-milk', pose, final: true }]);
});

test('a dragged robot stays on the floor and a target takes the dragged pose', async () => {
  const { root, page, scene } = await openPage();
  block(root, 'navigate').click();
  const lifted = [1, 2, 0.5, 0, 0, Math.sin(0.25), Math.cos(0.25)];
  const robot = page.state.activeRobot()[PlannedRobotKey.IDENTIFIER];
  scene().listeners.onPlace(new Selection(MarkerKind.ROBOT, robot), lifted);
  scene().listeners.onPlace(new Selection(MarkerKind.TARGET, page.state.steps()[0][PlanStepKey.IDENTIFIER], 'target_location'), lifted);
  const pose = page.state.robot(robot)[PlannedRobotKey.POSE];
  assert.deepEqual(PlanPose.position(pose), [1, 2, 0]);
  assert.ok(Math.abs(PlanPose.yaw(pose) - 0.5) < 1e-9);
  assert.deepEqual(page.state.steps()[0][PlanStepKey.VALUES].target_location, lifted);
});

test('a picked object is marked in the list and the turn mode reaches the view', async () => {
  const { root, page, scene } = await openPage();
  byAction(root, PlanAction.ADD_OBJECT)[0].click();
  const milk = page.state.objects()[0][PlannedObjectKey.IDENTIFIER];
  scene().listeners.onPick(new Selection(MarkerKind.OBJECT, milk));
  assert.equal(root.findAll((element) => element.dataset.object === milk)[0].className, 'object selected');
  byAction(root, PlanAction.TURN)[0].click();
  assert.equal(scene().mode, TransformMode.TURN);
  byAction(root, PlanAction.FRAME)[0].click();
  assert.equal(scene().framed, 1);
  byAction(root, PlanAction.SELECT_OBJECT)[0].click();
  assert.equal(scene().selected.identifier, milk);
});

// %% running

test('a performing run shows the live statuses and attaches its constraints once', async () => {
  const { root, page, live, timer } = await openPage();
  byAction(root, PlanAction.ADD_OBJECT)[0].click();
  block(root, 'park_arms').click();
  block(root, 'pick_up').click();
  drop(steps(root)[1], DragText.of(DragKind.CONSTRAINT, RULES[0][ConstraintRuleKey.SENTENCE]));
  await settled();
  byAction(root, PlanAction.PERFORM)[0].click();
  await settled();
  await timer.tick();
  await timer.tick();
  const statuses = root.findAll((element) => element.className === 'node-status').map((element) => element.textContent);
  assert.deepEqual(statuses, ['SUCCEEDED', 'RUNNING']);
  assert.equal(live.attached.length, 1);
  assert.equal(live.attached[0][ConstraintRequestKey.TEXT], page.state.steps()[1][PlanStepKey.CONSTRAINTS][0][StepConstraintKey.TEXT]);
  assert.deepEqual(root.findAll((element) => element.className === 'observation').map((element) => element.textContent), ['TRUE']);
  assert.match(root.findAll((element) => element.className === 'run-state')[0].textContent, /live/);
});

test('live poses are captured into the plan and the surfaces offered', async () => {
  const { root, page, live, timer } = await openPage();
  addMilk(root);
  block(root, 'transport').click();
  byAction(root, PlanAction.STAGE)[0].click();
  await settled();
  await timer.tick();
  byAction(root, PlanAction.CAPTURE)[0].click();
  const milk = page.state.objects()[0];
  assert.deepEqual(milk[PlannedObjectKey.POSE], live.world.captured.objects['key-milk']);
  const robot = page.state.activeRobot();
  assert.deepEqual(robot[PlannedRobotKey.POSE], live.world.robots.robots[0].pose);
  assert.deepEqual(robot[PlannedRobotKey.JOINT_POSITIONS], live.world.robots.robots[0].jointPositions);
  const table = live.world.surfaces.surfaces[0].type;
  page.state.setValue(page.state.steps()[0][PlanStepKey.IDENTIFIER], 'target_location', { [DestinationKey.PLACEMENT]: PlacementMode.SURFACE, [DestinationKey.SURFACE_TYPE]: table });
  page.render();
  const which = parameter(root, DestinationKey.SURFACE_NAME);
  assert.deepEqual(which.children.map((option) => option.value), ['', 'lab/table', 'lab/side_table']);
});

test('the live robot pose becomes a pose target, once there is one', async () => {
  const { root, page, timer } = await openPage();
  block(root, 'navigate').click();
  byAction(root, PlanAction.USE_LIVE_POSE)[0].click();
  assert.match(message(root), /live scene/);
  byAction(root, PlanAction.STAGE)[0].click();
  await settled();
  await timer.tick();
  byAction(root, PlanAction.USE_LIVE_POSE)[0].click();
  assert.deepEqual(page.state.steps()[0][PlanStepKey.VALUES].target_location, [0.5, -0.25, 0, 0, 0, 0, 1]);
});

test('capturing without a live world says so, and stopping ends the run', async () => {
  const { root, api, timer } = await openPage();
  byAction(root, PlanAction.CAPTURE)[0].click();
  assert.match(message(root), /live scene/);
  byAction(root, PlanAction.STAGE)[0].click();
  await settled();
  byAction(root, PlanAction.STOP)[0].click();
  await settled();
  await timer.tick();
  assert.equal(api.stopped, 1);
  assert.equal(root.findAll((element) => element.className === 'run-state')[0].dataset.state, RunState.STOPPED);
});

// %% plans and demos

test('a saved plan keeps its identity and is offered to open', async () => {
  const { root, api } = await openPage();
  byAction(root, PlanAction.SAVE)[0].click();
  await settled();
  byAction(root, PlanAction.SAVE)[0].click();
  await settled();
  assert.deepEqual(api.saved.map((record) => record[PlanRecordKey.IDENTIFIER]), ['plan-1', 'plan-1']);
  const choices = byAction(root, PlanAction.OPEN)[0].children.map((option) => option.value);
  assert.deepEqual(choices, ['', 'plan-1', 'plan-1']);
  const open = byAction(root, PlanAction.OPEN)[0];
  open.value = 'plan-1';
  open.dispatch(DomEvent.CHANGE);
  await settled();
  byAction(root, PlanAction.NEW)[0].click();
  assert.match(message(root), /New plan/);
});

test('the generated demo is shown and written', async () => {
  const { root, page } = await openPage();
  byAction(root, PlanAction.SHOW_DEMO)[0].click();
  await settled();
  const output = root.findAll((element) => element.className === 'demo-source')[0];
  assert.equal(output.hidden, false);
  assert.match(output.textContent, new RegExp(page.state.field(PlanKey.NAME)));
  byAction(root, PlanAction.WRITE_DEMO)[0].click();
  await settled();
  assert.match(message(root), /python \/demos\//);
});

test('disposing the page stops polling and releases the view', async () => {
  const { root, page, timer, scene } = await openPage();
  page.dispose();
  assert.equal(timer.callbacks.size, 0);
  assert.equal(scene().disposed, true);
  assert.equal(byAction(root, PlanAction.SAVE)[0].listenerCount(DomEvent.CLICK), 0);
});

// %% panel

test('the panel is the plan view: its heading and the recorded plan, nothing else', () => {
  const document = new FakeDocument();
  const bus = new EventBus();
  const panels = new PanelHost(document.createElement('nav'), document.createElement('div'));
  const panel = register({ bus, panels }, document);
  bus.publish(ViewerEvent.SCENE_LOADING, 'lab');
  assert.equal(PANEL_TITLE, 'Plan View');
  assert.equal(panel.element.children[0].textContent, PANEL_TITLE);
  assert.equal(panel.element.children.length, 2);
  assert.equal(panel.element.findAll((element) => element.tagName === 'A').length, 0);
  panel.dispose();
});

test('unfolded options stay unfolded while the plan changes', async () => {
  const { root } = await openPage();
  block(root, 'park_arms').click();
  const more = root.findAll((element) => element.className === 'more-options')[0];
  more.open = true;
  more.dispatch(DomEvent.TOGGLE);
  block(root, 'move_torso').click();
  assert.equal(root.findAll((element) => element.className === 'more-options')[0].open, true);
  const unfolded = root.findAll((element) => element.className === 'more-options')[0];
  unfolded.open = false;
  unfolded.dispatch(DomEvent.TOGGLE);
  block(root, 'move_torso').click();
  assert.equal(root.findAll((element) => element.className === 'more-options')[0].open, false);
});
