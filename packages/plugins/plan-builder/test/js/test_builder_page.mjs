import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  ConstraintRequestKey,
  ConstraintRuleKey,
  ConstraintTextKey,
  DemoSourceKey,
  PageState,
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
  StepKind,
  ViewerEvent,
} from 'cramera-viewer/protocol.js';
import { EventBus } from 'cramera-viewer/core/event-bus.js';
import { PanelHost } from 'cramera-viewer/panels/panel-host.js';
import { BuilderEnvironment, BuilderPage, ROBOT_MODEL_KEY } from '../../src/cramera_plan_builder/web/builder/builder-page.js';
import { SENTENCES_KEY } from '../../src/cramera_plan_builder/web/builder/constraints-view.js';
import { DRAG_MEDIA_TYPE, DragKind, DragText, DomEvent, PlanAction } from '../../src/cramera_plan_builder/web/builder/elements.js';
import { MarkerKind, Selection, TransformMode } from '../../src/cramera_plan_builder/web/builder/plan-scene.js';
import { PlanPose } from '../../src/cramera_plan_builder/web/builder/poses.js';
import { STEP_LABELS } from '../../src/cramera_plan_builder/web/builder/steps-view.js';
import { PANEL_TITLE, register } from '../../src/cramera_plan_builder/web/index.js';
import { FakeDocument, FakeStorage } from 'cramera-testing/fake-document.mjs';

const read = (name) => JSON.parse(readFileSync(new URL(name, import.meta.url), 'utf8'));
const RULES = read('../../src/cramera_plan_builder/rules/constraints.json').rules;
const byAction = (root, action) => root.findAll((element) => element.dataset.action === action);
const settled = () => new Promise((resolve) => setImmediate(resolve));
const drop = (element, text) => element.dispatch(DomEvent.DROP, { dataTransfer: { getData: (type) => (type === DRAG_MEDIA_TYPE ? text : '') } });

/**
 * Answers the page's requests and records what it asked.
 */
class FakeApi {
  constructor() {
    this.catalogAnswer = { ...read('dataset/catalog.json'), [PlanBuilderCatalogKey.CONSTRAINT_RULES]: RULES };
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
    if (rule && request[ConstraintTextKey.STEP_KIND]) compiled[StepConstraintKey.MONITOR] = { type: rule[ConstraintRuleKey.MONITOR_TYPE], params: {} };
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
const block = (root, kind) => root.findAll((element) => element.dataset.kind === kind)[0];
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
  assert.equal(byAction(root, PlanAction.ADD_STEP).length, page.state.offeredSteps(page.state.activeRobot()).length);
  assert.equal(timer.callbacks.size, 1);
});

test('the page starts in the environment its query names, with the last robot model', async () => {
  const { page } = await openPage(`${PlanBuilderPageParameter.ENVIRONMENT}=nowhere`, ({ storage }) => storage.setItem(ROBOT_MODEL_KEY, 'Tracy'));
  assert.equal(page.state.activeRobot()[PlannedRobotKey.MODEL], 'Tracy');
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
  block(root, StepKind.PARK_ARMS).click();
  drop(steps(root)[0], DragText.of(DragKind.STEP, StepKind.MOVE_TORSO));
  assert.deepEqual(page.state.steps().map((step) => step[PlanStepKey.KIND]), [StepKind.MOVE_TORSO, StepKind.PARK_ARMS]);
  assert.equal(steps(root)[0].findAll((element) => element.className === 'step-name')[0].textContent, STEP_LABELS[StepKind.MOVE_TORSO]);
});

test('a step is moved and removed with its controls', async () => {
  const { root, page } = await openPage();
  block(root, StepKind.PARK_ARMS).click();
  block(root, StepKind.MOVE_TORSO).click();
  byAction(root, PlanAction.MOVE_STEP_DOWN)[0].click();
  assert.equal(page.state.steps()[0][PlanStepKey.KIND], StepKind.MOVE_TORSO);
  byAction(root, PlanAction.REMOVE_STEP)[0].click();
  assert.deepEqual(page.state.steps().map((step) => step[PlanStepKey.KIND]), [StepKind.PARK_ARMS]);
});

test('a refused edit is reported', async () => {
  const { root, page } = await openPage();
  for (let count = 0; count <= page.state.limits.maximumSteps; count += 1) block(root, StepKind.PARK_ARMS).click();
  assert.match(message(root), /At most/);
});

test('a dropped sentence is compiled for its step and attached', async () => {
  const { root, page, api } = await openPage();
  byAction(root, PlanAction.ADD_OBJECT)[0].click();
  block(root, StepKind.PICK_UP).click();
  drop(steps(root)[0], DragText.of(DragKind.CONSTRAINT, RULES[0][ConstraintRuleKey.SENTENCE]));
  await settled();
  const [request] = api.compiled;
  assert.equal(request[ConstraintTextKey.STEP_KIND], StepKind.PICK_UP);
  assert.equal(request[ConstraintTextKey.STEP_OBJECT], page.state.objects()[0][PlannedObjectKey.IDENTIFIER]);
  assert.equal(page.state.steps()[0][PlanStepKey.CONSTRAINTS][0][StepConstraintKey.MONITOR_TYPE], RULES[0][ConstraintRuleKey.MONITOR_TYPE]);
  assert.equal(root.findAll((element) => element.className === 'chip').length, 1);
});

test('a sentence no rule reads is not attached', async () => {
  const { root, page } = await openPage();
  block(root, StepKind.PARK_ARMS).click();
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

test('the name and the environment are edited in the bar', async () => {
  const { root, page, scene } = await openPage();
  const name = byAction(root, PlanAction.NAME)[0];
  name.value = 'milk_run';
  name.dispatch(DomEvent.CHANGE);
  const environment = byAction(root, PlanAction.ENVIRONMENT)[0];
  environment.value = '';
  environment.dispatch(DomEvent.CHANGE);
  assert.equal(page.state.field(PlanKey.NAME), 'milk_run');
  assert.equal(page.state.field(PlanKey.ENVIRONMENT), '');
  assert.deepEqual(scene().environments.at(-1), null);
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

test('a dragged robot or navigation target stays on the floor', async () => {
  const { root, page, scene } = await openPage();
  block(root, StepKind.NAVIGATE).click();
  const lifted = [1, 2, 0.5, 0, 0, Math.sin(0.25), Math.cos(0.25)];
  const robot = page.state.activeRobot()[PlannedRobotKey.IDENTIFIER];
  scene().listeners.onPlace(new Selection(MarkerKind.ROBOT, robot), lifted);
  scene().listeners.onPlace(new Selection(MarkerKind.TARGET, page.state.steps()[0][PlanStepKey.IDENTIFIER]), lifted);
  for (const pose of [page.state.robot(robot)[PlannedRobotKey.POSE], page.state.steps()[0][PlanStepKey.TARGET]]) {
    assert.deepEqual(PlanPose.position(pose), [1, 2, 0]);
    assert.ok(Math.abs(PlanPose.yaw(pose) - 0.5) < 1e-9);
  }
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
  block(root, StepKind.PARK_ARMS).click();
  block(root, StepKind.PICK_UP).click();
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
  block(root, StepKind.TRANSPORT).click();
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
  page.state.updateStep(page.state.steps()[0][PlanStepKey.IDENTIFIER], { [PlanStepKey.PLACEMENT]: PlacementMode.SURFACE, [PlanStepKey.SURFACE_TYPE]: table });
  page.render();
  const which = byAction(root, PlanAction.STEP_PARAMETER).at(-1);
  assert.deepEqual(which.children.map((option) => option.value), ['', 'lab/table', 'lab/side_table']);
});

test('the live robot pose becomes a navigation target, once there is one', async () => {
  const { root, page, timer } = await openPage();
  block(root, StepKind.NAVIGATE).click();
  byAction(root, PlanAction.USE_LIVE_POSE)[0].click();
  assert.match(message(root), /live scene/);
  byAction(root, PlanAction.STAGE)[0].click();
  await settled();
  await timer.tick();
  byAction(root, PlanAction.USE_LIVE_POSE)[0].click();
  assert.deepEqual(page.state.steps()[0][PlanStepKey.TARGET], [0.5, -0.25, 0, 0, 0, 0, 1]);
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

test('the panel links to the builder page and to planning in the shown scene', () => {
  const document = new FakeDocument();
  const bus = new EventBus();
  const panels = new PanelHost(document.createElement('nav'), document.createElement('div'));
  const panel = register({ bus, panels }, document, 'http://localhost/plugins/plan-builder/builder.html');
  bus.publish(ViewerEvent.SCENE_LOADING, 'lab');
  const [, , , line] = panel.element.children;
  assert.equal(line.hidden, false);
  assert.match(line.children[0].href, new RegExp(`${PlanBuilderPageParameter.ENVIRONMENT}=lab`));
  assert.equal(panel.element.children[0].textContent, PANEL_TITLE);
  panel.dispose();
});
