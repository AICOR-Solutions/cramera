import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  ActionCatalogKey,
  ActionSchemaKey,
  DetectedObjectText,
  DetectionGrounding,
  DetectionRegionKey,
  RegionKind,
  SceneScanKey,
  ConstraintRequestKey,
  ConstraintRuleKey,
  ConstraintTextKey,
  DemoSourceKey,
  PageState,
  DestinationKey,
  EnvironmentAnnotationsKey,
  SurfaceKey,
  IndexEntryKey,
  LoadedEnvironmentKey,
  UrdfFolderKey,
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
  RunEventKey,
  RunEventKind,
  ArmReportKey,
  RobotPostureKey,
  RunStatusKey,
  SafetyStopKey,
  StepState,
  SavedDemoKey,
  StepConstraintKey,
  StepFailureReason,
  StepValidationKey,
  StepVerdict,
  ValidationReportKey,
  ViewerEvent,
  RobotProfileKey,
  ExecutorKind,
  SkillKey,
  PlanTemplateKey,
  ZoneKey,
} from 'cramera-viewer/protocol.js';
import { EventBus } from 'cramera-viewer/core/event-bus.js';
import { PollInterval } from 'cramera-viewer/live/live-session.js';
import { PanelHost } from 'cramera-viewer/panels/panel-host.js';
import { BuilderEnvironment, BuilderPage, DEVELOPER_MODE_KEY, ROBOT_MODEL_KEY, SCENE_TOLERANCE, URDF_FOLDER_KEY, loadedMessage, scanMessage } from '../../src/cramera_plan_builder/web/builder/builder-page.js';
import { SENTENCES_KEY } from '../../src/cramera_plan_builder/web/builder/constraints-view.js';
import { DRAG_MEDIA_TYPE, DragKind, DragText, DomEvent, PlanAction } from '../../src/cramera_plan_builder/web/builder/elements.js';
import { MarkerKind, Selection, TransformMode } from '../../src/cramera_plan_builder/web/builder/plan-scene.js';
import { PlanPose } from '../../src/cramera_plan_builder/web/builder/poses.js';
import { EMPTY_FOLDER, EnvironmentNote, RobotsNote } from '../../src/cramera_plan_builder/web/builder/robots-view.js';
import { REASON_TEXTS, STEP_PALETTE_SIZE, noAnnotation } from '../../src/cramera_plan_builder/web/builder/steps-view.js';
import { SafetyStopBanner } from '../../src/cramera_plan_builder/web/builder/safety-stop.js';
import { RequestRefused } from '../../src/cramera_plan_builder/web/builder/builder-api.js';
import { PANEL_TITLE, register } from '../../src/cramera_plan_builder/web/index.js';
import { FakeDocument, FakeStorage } from 'cramera-testing/fake-document.mjs';

const read = (name) => JSON.parse(readFileSync(new URL(name, import.meta.url), 'utf8'));
const RULES = read('../../src/cramera_plan_builder/rules/constraints.json').rules;
const TRACY_REACH = read('dataset/tracy_reach.json');
const ACTIONS = read('../dataset/actions.json');
const byAction = (root, action) => root.findAll((element) => element.dataset.action === action);
const settled = () => new Promise((resolve) => setImmediate(resolve));
const drop = (element, text) => element.dispatch(DomEvent.DROP, { dataTransfer: { getData: (type) => (type === DRAG_MEDIA_TYPE ? text : '') } });

/**
 * The folders the fake viewer's machine holds, by path.
 */
const FOLDERS = {
  '/home/vee': { [UrdfFolderKey.PARENT]: '/home', [UrdfFolderKey.FOLDERS]: ['worlds'], [UrdfFolderKey.FILES]: [] },
  '/home/vee/worlds': { [UrdfFolderKey.PARENT]: '/home/vee', [UrdfFolderKey.FOLDERS]: [], [UrdfFolderKey.FILES]: ['apartment.urdf', 'kitchen.urdf'] },
  '/': { [UrdfFolderKey.PARENT]: null, [UrdfFolderKey.FOLDERS]: [], [UrdfFolderKey.FILES]: [] },
};

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
    this.loaded = [];
    this.listed = [];
    this.annotationsAsked = [];
    this.annotationsAnswer = { [EnvironmentAnnotationsKey.ANNOTATIONS]: [] };
    this.validated = [];
    this.validationAnswer = (steps) => steps.map((step) => ({ [StepValidationKey.STEP]: step[PlanStepKey.IDENTIFIER], [StepValidationKey.VERDICT]: StepVerdict.VALID }));
    this.reached = [];
    this.scanned = [];
    this.scanAnswer = { [SceneScanKey.OBJECTS]: [], [SceneScanKey.GROUNDING]: DetectionGrounding.PERCEIVED, [SceneScanKey.UNRECOGNIZED]: 0 };
    this.mirrored = {};
    this.mirroredArms = null;
    this.postureFails = false;
  }

  async posture() {
    if (this.postureFails) throw new TypeError('Failed to fetch');
    const posture = { [RobotPostureKey.JOINT_POSITIONS]: structuredClone(this.mirrored) };
    if (this.mirroredArms === null) return posture;
    return { ...posture, [RobotPostureKey.ARMS]: structuredClone(this.mirroredArms), [RobotPostureKey.MIRRORED]: true };
  }

  async validate(plan) {
    this.validated.push(plan);
    const robot = plan[PlanKey.ROBOTS].find((candidate) => candidate[PlannedRobotKey.IDENTIFIER] === plan[PlanKey.SELECTED_ROBOT]) ?? plan[PlanKey.ROBOTS][0];
    return { [ValidationReportKey.STEPS]: this.validationAnswer(robot[PlannedRobotKey.STEPS]), [ValidationReportKey.SECONDS]: 2.5 };
  }

  async reach(model) {
    this.reached.push(model);
    return structuredClone(TRACY_REACH);
  }

  async scan(plan, region) {
    this.scanned.push({ plan, region });
    return structuredClone(this.scanAnswer);
  }

  async environmentAnnotations(environment) {
    this.annotationsAsked.push(environment);
    return structuredClone(this.annotationsAnswer);
  }

  async urdfFolder(path) {
    this.listed.push(path);
    const folder = FOLDERS[path ?? '/home/vee'];
    if (!folder) throw new Error(`'${path}' is no folder on the viewer's machine.`);
    return { [UrdfFolderKey.PATH]: path ?? '/home/vee', ...folder };
  }

  async loadEnvironment(path) {
    this.loaded.push(path);
    if (!path.endsWith('.urdf')) throw new Error(`'${path}' is no URDF or xacro file on the viewer's machine.`);
    const name = path.split('/').at(-1).replace('.urdf', '');
    return { [LoadedEnvironmentKey.ENTRY]: { [IndexEntryKey.NAME]: name, [IndexEntryKey.ENVIRONMENT]: name }, [LoadedEnvironmentKey.MISSING_MESHES]: [] };
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

  async run(plan, mode, overrideValidation = false) {
    this.runs.push({ plan, mode, overrideValidation });
    this.status = { [RunStatusKey.STATE]: RunState.RUNNING, [RunStatusKey.MODE]: mode, [RunStatusKey.LOG]: 'building the world' };
    return structuredClone(this.status);
  }

  async runStatus() {
    return structuredClone(this.status);
  }

  async acknowledge() {
    this.acknowledged = (this.acknowledged ?? 0) + 1;
    const stop = this.status[RunStatusKey.SAFETY_STOP];
    if (stop) this.status = { ...this.status, [RunStatusKey.SAFETY_STOP]: { ...stop, [SafetyStopKey.ACKNOWLEDGED]: true } };
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

  show(state, live, overlay) {
    this.shown = { document: state.document, live, overlay };
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
    this.intervals = new Map();
    this.next = 1;
  }

  repeat(callback, interval) {
    const handle = this.next++;
    this.callbacks.set(handle, callback);
    this.intervals.set(handle, interval);
    return handle;
  }

  cancel(handle) {
    this.callbacks.delete(handle);
    this.intervals.delete(handle);
  }

  /**
   * Run only the callbacks repeated every `interval` milliseconds.
   * @param {number} interval The interval in milliseconds.
   */
  async tickEvery(interval) {
    for (const [handle, callback] of [...this.callbacks]) if (this.intervals.get(handle) === interval) await callback();
    await settled();
  }

  async tick() {
    for (const callback of [...this.callbacks.values()]) await callback();
    await settled();
  }
}

/**
 * Open the page, by default adding one robot as the person would.
 * @param {string} query The page's query.
 * @param {function(Object): void} prepare Prepares the fake API and storage.
 * @param {{robot: boolean}} options Whether to add a robot once the page started.
 */
async function openPage(query = '', prepare = () => {}, { robot = true } = {}) {
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
  if (robot) byAction(root, PlanAction.ADD_ROBOT)[0]?.click();
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
  assert.equal(timer.callbacks.size, 2);
});

test('the page starts in the environment its query names, with the last robot model', async () => {
  const { page } = await openPage(`${PlanBuilderPageParameter.ENVIRONMENT}=nowhere`, ({ storage }) => storage.setItem(ROBOT_MODEL_KEY, 'tracy'));
  assert.equal(page.state.activeRobot()[PlannedRobotKey.MODEL], 'tracy');
  assert.equal(page.state.field(PlanKey.ENVIRONMENT), 'lab');
});

test('the page starts with the robot and environment of the configured profile', async () => {
  const { page, root } = await openPage('', ({ api }) => {
    api.catalogAnswer[PlanBuilderCatalogKey.PROFILE] = { [RobotProfileKey.ROBOT]: 'tracy', [RobotProfileKey.LABEL]: 'Tracy', [RobotProfileKey.ENVIRONMENT]: 'lab' };
  }, { robot: false });
  assert.equal(page.state.activeRobot()[PlannedRobotKey.MODEL], 'tracy');
  assert.equal(page.state.field(PlanKey.ENVIRONMENT), 'lab');
  byAction(root, PlanAction.NEW)[0].click();
  assert.deepEqual(page.state.robots().map((robot) => robot[PlannedRobotKey.MODEL]), ['tracy']);
});

test('the page opens the saved plan its query names', async () => {
  const { page } = await openPage(`${PlanBuilderPageParameter.PLAN}=plan-1`, ({ api }) => {
    api.saved.push({ [PlanRecordKey.IDENTIFIER]: 'plan-1', [PlanRecordKey.DOCUMENT]: { [PlanKey.NAME]: 'opened', [PlanKey.ROBOTS]: [] } });
  }, { robot: false });
  assert.equal(page.state.field(PlanKey.NAME), 'opened');
});

test('without the CRAM workspace the page composes but does not run', async () => {
  const { document, root } = await openPage('', ({ api }) => {
    api.catalogAnswer[PlanBuilderCatalogKey.MISSING] = ['coraplex'];
  });
  assert.match(document.documentElement.dataset[PageStateAttribute.STATUS], /coraplex/);
  assert.equal(byAction(root, PlanAction.STAGE)[0].disabled, true);
  assert.equal(byAction(root, PlanAction.PERFORM)[0].disabled, true);
  assert.equal(byAction(root, PlanAction.SIMULATE)[0].disabled, true);
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
  assert.match(reasons.get('move_torso'), /torso_state/);
  const notice = root.findAll((element) => element.className === 'notice')[0];
  assert.match(notice.textContent, new RegExp(ACTIONS[ActionCatalogKey.FAILED_MODULES][0].module));
});

test('a gripper step offers its enumerations with the choices of the robot', async () => {
  const { root, page } = await openPage('', ({ storage }) => storage.setItem(ROBOT_MODEL_KEY, 'stretch'));
  block(root, 'set_gripper').click();
  const gripper = parameter(root, 'gripper');
  const motion = parameter(root, 'motion');
  assert.deepEqual(gripper.children.map((option) => option.value), ['both']);
  assert.deepEqual(motion.children.map((option) => option.value), ['open', 'close', 'medium']);
  motion.value = 'close';
  motion.dispatch(DomEvent.CHANGE);
  assert.equal(page.state.steps()[0][PlanStepKey.VALUES].motion, 'close');
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
  assert.ok(root.findAll((element) => element.className === 'empty').some((element) => element.textContent === noAnnotation('tool')));
  tool.value = 'knife';
  tool.dispatch(DomEvent.CHANGE);
  assert.equal(page.state.steps()[0][PlanStepKey.VALUES].tool, 'knife');
  const stride = parameter(root, 'pointer_stride');
  stride.value = '2.6';
  stride.dispatch(DomEvent.CHANGE);
  assert.equal(page.state.steps()[0][PlanStepKey.VALUES].pointer_stride, 3);
});

test('an annotation field offers the environment\'s annotations of its class', async () => {
  const { root, page, api } = await openPage('', ({ api }) => {
    api.annotationsAnswer[EnvironmentAnnotationsKey.ANNOTATIONS] = [
      { [SurfaceKey.TYPE]: 'tool', [SurfaceKey.NAME]: 'knife_block_knife' },
      { [SurfaceKey.TYPE]: 'tool', [SurfaceKey.NAME]: 'drawer_knife' },
      { [SurfaceKey.TYPE]: 'handle', [SurfaceKey.NAME]: 'handle_cab1_top_door' },
    ];
  });
  await settled();
  assert.deepEqual(api.annotationsAsked, [page.state.field(PlanKey.ENVIRONMENT)]);
  byAction(root, PlanAction.ADD_OBJECT)[0].click();
  block(root, 'cutting').click();
  const tool = parameter(root, 'tool');
  assert.equal(tool.tagName, 'SELECT');
  assert.deepEqual(tool.children.map((option) => option.value).slice(1), ['knife_block_knife', 'drawer_knife']);
  tool.value = 'drawer_knife';
  tool.dispatch(DomEvent.CHANGE);
  assert.equal(page.state.steps()[0][PlanStepKey.VALUES].tool, 'drawer_knife');
});

test('the empty floor offers no annotations and asks for none', async () => {
  const { root, api } = await openPage();
  await settled();
  const environment = byAction(root, PlanAction.ENVIRONMENT)[0];
  environment.value = '';
  environment.dispatch(DomEvent.CHANGE);
  await settled();
  assert.equal(api.annotationsAsked.length, 1);
  byAction(root, PlanAction.ADD_OBJECT)[0].click();
  block(root, 'cutting').click();
  assert.equal(parameter(root, 'tool').tagName, 'INPUT');
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
  }, { robot: false });
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

test('a URDF loaded from its path is offered and becomes the environment', async () => {
  const { root, page, api, scene } = await openPage();
  const path = byAction(root, PlanAction.URDF_PATH)[0];
  path.value = '  /worlds/apartment.urdf ';
  byAction(root, PlanAction.LOAD_URDF)[0].click();
  await settled();
  assert.deepEqual(api.loaded, ['/worlds/apartment.urdf']);
  assert.equal(page.state.field(PlanKey.ENVIRONMENT), 'apartment');
  const offered = byAction(root, PlanAction.ENVIRONMENT)[0].children.map((option) => option.value);
  assert.deepEqual(offered.slice(-1), ['apartment']);
  assert.equal(environmentNote(root), EnvironmentNote.chosen('apartment'));
  assert.equal(scene().environments.at(-1), 'apartment');
  assert.equal(message(root), 'Loaded apartment.');
});

test('a path the viewer refuses keeps the environment and says why', async () => {
  const { root, page, api } = await openPage();
  const chosen = page.state.field(PlanKey.ENVIRONMENT);
  byAction(root, PlanAction.LOAD_URDF)[0].click();
  assert.deepEqual(api.loaded, []);
  byAction(root, PlanAction.URDF_PATH)[0].value = '/worlds/apartment.stl';
  byAction(root, PlanAction.LOAD_URDF)[0].click();
  await settled();
  assert.equal(page.state.field(PlanKey.ENVIRONMENT), chosen);
  assert.match(message(root), /no URDF or xacro file/);
});

const picker = (root) => root.findAll((element) => element.className === 'urdf-picker')[0];
const pickerButton = (root, action, name) => byAction(root, action).find((element) => element.dataset.name === name);

test('the picker browses folders and a picked URDF becomes the environment', async () => {
  const { root, page, api, storage } = await openPage();
  assert.equal(picker(root).hidden, true);
  byAction(root, PlanAction.BROWSE_URDF)[0].click();
  await settled();
  assert.equal(picker(root).hidden, false);
  assert.deepEqual(api.listed, [null]);
  pickerButton(root, PlanAction.OPEN_FOLDER, 'worlds').click();
  await settled();
  assert.deepEqual(byAction(root, PlanAction.PICK_URDF).map((button) => button.dataset.name), ['apartment.urdf', 'kitchen.urdf']);
  assert.equal(storage.getItem(URDF_FOLDER_KEY), '/home/vee/worlds');
  pickerButton(root, PlanAction.PICK_URDF, 'kitchen.urdf').click();
  await settled();
  assert.deepEqual(api.loaded, ['/home/vee/worlds/kitchen.urdf']);
  assert.equal(byAction(root, PlanAction.URDF_PATH)[0].value, '/home/vee/worlds/kitchen.urdf');
  assert.equal(page.state.field(PlanKey.ENVIRONMENT), 'kitchen');
  assert.equal(picker(root).hidden, true);
});

test('the picker opens on the folder it showed last, goes up and closes', async () => {
  const { root, api } = await openPage('', ({ storage }) => storage.setItem(URDF_FOLDER_KEY, '/home/vee/worlds'));
  byAction(root, PlanAction.BROWSE_URDF)[0].click();
  await settled();
  assert.deepEqual(api.listed, ['/home/vee/worlds']);
  byAction(root, PlanAction.FOLDER_UP)[0].click();
  await settled();
  assert.deepEqual(api.listed.at(-1), '/home/vee');
  byAction(root, PlanAction.CLOSE_PICKER)[0].click();
  assert.equal(picker(root).hidden, true);
});

test('a remembered folder that is gone opens the home folder', async () => {
  const { root, api } = await openPage('', ({ storage }) => storage.setItem(URDF_FOLDER_KEY, '/gone'));
  byAction(root, PlanAction.BROWSE_URDF)[0].click();
  await settled();
  assert.deepEqual(api.listed, ['/gone', null]);
  assert.ok(pickerButton(root, PlanAction.OPEN_FOLDER, 'worlds'));
});

test('the root has no way up and an empty folder says so', async () => {
  const { root } = await openPage('', ({ storage }) => storage.setItem(URDF_FOLDER_KEY, '/'));
  byAction(root, PlanAction.BROWSE_URDF)[0].click();
  await settled();
  assert.equal(byAction(root, PlanAction.FOLDER_UP)[0].disabled, true);
  assert.equal(picker(root).findAll((element) => element.textContent === EMPTY_FOLDER).length, 1);
});

test('a loaded environment names its first missing meshes', () => {
  assert.equal(loadedMessage('apartment', ['a.dae']), 'Loaded apartment; 1 mesh it names was not found and left out: a.dae');
  assert.match(loadedMessage('apartment', ['a', 'b', 'c', 'd']), /4 meshes .*: a, b, c, …$/);
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

test('a new plan starts without a robot, and the last robot can be removed', async () => {
  const { root, page } = await openPage('', () => {}, { robot: false });
  assert.deepEqual(page.state.robots(), []);
  assert.ok(root.findAll((element) => element.textContent === RobotsNote.NONE_ADDED).length === 1);
  assert.equal(root.findAll((element) => element.tagName === 'H2' && element.textContent === 'Plan of no robot').length, 1);
  byAction(root, PlanAction.ADD_ROBOT)[0].click();
  assert.equal(page.state.robots().length, 1);
  byAction(root, PlanAction.REMOVE_ROBOT)[0].click();
  assert.deepEqual(page.state.robots(), []);
  assert.equal(page.state.activeRobot(), null);
});

test('a new plan from the bar starts without a robot too', async () => {
  const { root, page } = await openPage();
  assert.equal(page.state.robots().length, 1);
  byAction(root, PlanAction.NEW)[0].click();
  await settled();
  assert.deepEqual(page.state.robots(), []);
});

test('a robot is added as the model the person used last', async () => {
  const { root, page } = await openPage('', ({ storage }) => storage.setItem(ROBOT_MODEL_KEY, 'tracy'), { robot: false });
  const [model] = byAction(root, PlanAction.ROBOT_MODEL);
  assert.equal(model.value, 'tracy');
  byAction(root, PlanAction.ADD_ROBOT)[0].click();
  assert.equal(page.state.activeRobot()[PlannedRobotKey.MODEL], 'tracy');
});

// %% detecting

const SCANNED_CUBES = [
  { [PlannedObjectKey.IDENTIFIER]: 'red_cube', [PlannedObjectKey.MODEL]: 'aicor/objects/cubes/red_cube/model.urdf', [PlannedObjectKey.POSE]: [0.55, 0.1, 0.909, 0, 0, 0, 1] },
  { [PlannedObjectKey.IDENTIFIER]: 'blue_cube', [PlannedObjectKey.MODEL]: 'aicor/objects/cubes/blue_cube/model.urdf', [PlannedObjectKey.POSE]: [0.55, 0.3, 0.909, 0, 0, 0, 1] },
];

test('scanning the scene fills the objects with what the robot finds', async () => {
  const { root, page, api } = await openPage();
  api.scanAnswer[SceneScanKey.OBJECTS] = SCANNED_CUBES;
  byAction(root, PlanAction.SCAN_SCENE)[0].click();
  await settled();
  assert.equal(api.scanned.length, 1);
  assert.deepEqual(page.state.objects(), SCANNED_CUBES);
  assert.equal(message(root), scanMessage(api.scanAnswer));
});

test('a scan assumed from the twin says it is checked again when the plan runs', () => {
  const scan = { [SceneScanKey.OBJECTS]: SCANNED_CUBES, [SceneScanKey.GROUNDING]: DetectionGrounding.ASSUMED, [SceneScanKey.UNRECOGNIZED]: 2 };
  assert.match(scanMessage(scan), /assumed from the twin.*perceived again when the plan runs.*2 more found/);
});

test('a detect step looks at the whole table', async () => {
  const { root, page } = await openPage();
  block(root, 'detect').click();
  assert.deepEqual(page.state.steps()[0][PlanStepKey.VALUES].region, { [DetectionRegionKey.KIND]: RegionKind.TABLE });
  assert.equal(parameter(root, 'region').value, RegionKind.TABLE);
});

test('a later step names the object a detect step finds', async () => {
  const { root, page } = await openPage();
  byAction(root, PlanAction.ADD_OBJECT)[0].click();
  block(root, 'detect').click();
  block(root, 'pick_up').click();
  const [detect, pick] = page.state.steps();
  const found = `${DetectedObjectText.PREFIX}${detect[PlanStepKey.IDENTIFIER]}`;
  const object = parameter(root, 'object_designator');
  assert.ok(object.children.map((option) => option.value).includes(found));
  object.value = found;
  object.dispatch(DomEvent.CHANGE);
  assert.equal(page.state.step(pick[PlanStepKey.IDENTIFIER])[PlanStepKey.VALUES].object_designator, found);
  assert.deepEqual(page.state.problems(page.state.step(pick[PlanStepKey.IDENTIFIER])), []);
});

test('a step before the detect step cannot name what it finds', async () => {
  const { root, page } = await openPage();
  byAction(root, PlanAction.ADD_OBJECT)[0].click();
  block(root, 'pick_up').click();
  block(root, 'detect').click();
  const [pick, detect] = page.state.steps();
  const choices = page.state.objectChoices(pick[PlanStepKey.IDENTIFIER]).map((choice) => choice.value);
  assert.equal(choices.includes(`${DetectedObjectText.PREFIX}${detect[PlanStepKey.IDENTIFIER]}`), false);
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

test('a robot whose root is its pelvis keeps its height when it is dragged or edited', async () => {
  const { root, page, scene } = await openPage('', ({ storage }) => storage.setItem(ROBOT_MODEL_KEY, 'unitree_g1'));
  const robot = page.state.activeRobot()[PlannedRobotKey.IDENTIFIER];
  scene().listeners.onPlace(new Selection(MarkerKind.ROBOT, robot), [1, 2, 0, 0, 0, 0, 1]);
  assert.deepEqual(PlanPose.position(page.state.robot(robot)[PlannedRobotKey.POSE]), [1, 2, 0.7923]);
  const x = byAction(root, PlanAction.POSE).find((input) => input.dataset.field === 'x');
  x.value = '3';
  x.dispatch(DomEvent.CHANGE);
  assert.deepEqual(PlanPose.position(page.state.robot(robot)[PlannedRobotKey.POSE]), [3, 2, 0.7923]);
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

test('a performing run moves the robot and the objects in the 3D view as often as the scene page', async () => {
  const { root, page, live, timer, scene } = await openPage();
  addMilk(root);
  byAction(root, PlanAction.PERFORM)[0].click();
  await settled();
  await timer.tick();
  const moved = structuredClone(live.world);
  moved.robots.robots[0].jointPositions = { 'robot_1/torso_lift_joint': 0.1 };
  moved.captured.objects['key-milk'] = [1.25, 0.5, 1.2, 0, 0, 0, 1];
  live.world = moved;
  await timer.tickEvery(PollInterval.STATE);
  const robot = page.state.activeRobot()[PlannedRobotKey.IDENTIFIER];
  const milk = page.state.objects()[0][PlannedObjectKey.IDENTIFIER];
  assert.deepEqual(scene().shown.live.postures.get(robot), moved.robots.robots[0].jointPositions);
  assert.deepEqual(scene().shown.live.objects.get(milk), moved.captured.objects['key-milk']);
});

test('without a run the robot stands in the posture the real robot reports', async () => {
  const { page, api, timer, scene } = await openPage();
  api.mirrored = { left_shoulder_pan_joint: 0.3 };
  await timer.tickEvery(PollInterval.STATE);
  const robot = page.state.activeRobot()[PlannedRobotKey.IDENTIFIER];
  assert.deepEqual(scene().shown.live.postures.get(robot), api.mirrored);

  api.mirrored = { left_shoulder_pan_joint: -0.4 };
  await timer.tickEvery(PollInterval.STATE);
  assert.deepEqual(scene().shown.live.postures.get(robot), api.mirrored);
});

const postureLine = (root) => root.findAll((element) => (element.className ?? '').includes('posture-state'))[0];
const arm = (name, age, live) => ({ [ArmReportKey.ARM]: name, ...(age === null ? {} : { [ArmReportKey.AGE_SECONDS]: age }), [ArmReportKey.LIVE]: live });

test('an arm whose driver went silent greys the robot and says so until it reports again', async () => {
  const { page, api, timer, scene, root } = await openPage();
  const robot = page.state.activeRobot()[PlannedRobotKey.IDENTIFIER];
  api.mirrored = { left_shoulder_pan_joint: 0.3 };
  api.mirroredArms = [arm('left_arm', 4.2, false), arm('right_arm', 0.05, true)];
  await timer.tickEvery(PollInterval.STATE);
  assert.deepEqual([...scene().shown.live.stale], [robot]);
  assert.equal(postureLine(root).hidden, false);
  assert.equal(postureLine(root).textContent, 'Left arm: no joint states for 5 s — the picture may not match the robot.');

  api.mirroredArms = [arm('left_arm', 0.05, true), arm('right_arm', 0.05, true)];
  await timer.tickEvery(PollInterval.STATE);
  assert.deepEqual([...scene().shown.live.stale], []);
  assert.equal(postureLine(root).hidden, true);
});

test('both arms silent, or never reported, are each named', async () => {
  const { api, timer, root } = await openPage();
  api.mirroredArms = [arm('left_arm', 2, false), arm('right_arm', null, false)];
  await timer.tickEvery(PollInterval.STATE);
  assert.equal(postureLine(root).textContent, 'Left arm: no joint states for 2 s; Right arm: no joint states yet — the picture may not match the robot.');
});

test('a mirror that never reported greys the robot', async () => {
  const { page, api, timer, scene, root } = await openPage();
  api.mirroredArms = [];
  await timer.tickEvery(PollInterval.STATE);
  assert.deepEqual([...scene().shown.live.stale], [page.state.activeRobot()[PlannedRobotKey.IDENTIFIER]]);
  assert.equal(postureLine(root).textContent, 'No joint states from the robot yet — the picture may not match the robot.');
});

test('a posture the plan builder no longer answers greys the robot', async () => {
  const { page, api, timer, scene, root } = await openPage();
  api.mirroredArms = [arm('left_arm', 0.05, true), arm('right_arm', 0.05, true)];
  await timer.tickEvery(PollInterval.STATE);
  api.postureFails = true;
  await timer.tickEvery(PollInterval.STATE);
  assert.deepEqual([...scene().shown.live.stale], [page.state.activeRobot()[PlannedRobotKey.IDENTIFIER]]);
  assert.equal(postureLine(root).textContent, 'The plan builder does not answer (Failed to fetch) — the picture may not match the robot.');
});

test('a simulated robot is never greyed for its posture', async () => {
  const { api, timer, scene, root } = await openPage();
  api.postureFails = true;
  await timer.tickEvery(PollInterval.STATE);
  assert.equal(scene().shown.live.stale?.size ?? 0, 0);
  assert.equal(postureLine(root).hidden, true);
});

test('a run in physics asks for the physics run mode and attaches its constraints', async () => {
  const { root, api, live, timer } = await openPage();
  byAction(root, PlanAction.ADD_OBJECT)[0].click();
  block(root, 'park_arms').click();
  block(root, 'pick_up').click();
  drop(steps(root)[1], DragText.of(DragKind.CONSTRAINT, RULES[0][ConstraintRuleKey.SENTENCE]));
  await settled();
  byAction(root, PlanAction.SIMULATE)[0].click();
  await settled();
  await timer.tick();
  assert.equal(api.runs[0].mode, RunMode.SIMULATE);
  assert.match(message(root), /physics/);
  assert.equal(live.attached.length, 1);
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

// %% robot profile

const SKILLED_PROFILE = {
  [RobotProfileKey.ROBOT]: 'tracy',
  [RobotProfileKey.LABEL]: 'Tracy',
  [RobotProfileKey.SKILLS]: [{ [SkillKey.IDENTIFIER]: 'park', [SkillKey.LABEL]: 'Park arms', [SkillKey.ACTION]: 'park_arms', [SkillKey.VALUES]: { arm: 'both' }, [SkillKey.FIELDS]: [] }],
};

test('with a profile of skills the palette offers skills until developer mode is on', async () => {
  const { root, page, storage } = await openPage('', ({ api }) => {
    api.catalogAnswer[PlanBuilderCatalogKey.PROFILE] = SKILLED_PROFILE;
  }, { robot: false });
  assert.equal(byAction(root, PlanAction.ADD_STEP).length, 0);
  byAction(root, PlanAction.ADD_SKILL)[0].click();
  assert.equal(page.state.steps()[0][PlanStepKey.SKILL], 'park');
  const developer = byAction(root, PlanAction.DEVELOPER_MODE)[0];
  developer.checked = true;
  developer.dispatch(DomEvent.CHANGE);
  assert.equal(byAction(root, PlanAction.ADD_SKILL).length, 0);
  assert.equal(byAction(root, PlanAction.ADD_STEP).length, page.state.offeredActions(page.state.activeRobot()).length);
  assert.equal(storage.getItem(DEVELOPER_MODE_KEY), 'true');
});

test('a template of the profile starts a new plan as its copy', async () => {
  const template = { [PlanKey.NAME]: 'Park both arms', [PlanKey.ROBOTS]: [] };
  const { root, page } = await openPage('', ({ api }) => {
    api.catalogAnswer[PlanBuilderCatalogKey.PROFILE] = SKILLED_PROFILE;
    api.catalogAnswer[PlanBuilderCatalogKey.TEMPLATES] = [{ [PlanTemplateKey.IDENTIFIER]: 'park', [PlanTemplateKey.PLAN]: template }];
  }, { robot: false });
  const picker = byAction(root, PlanAction.NEW_FROM_TEMPLATE)[0];
  picker.value = 'park';
  picker.dispatch(DomEvent.CHANGE);
  assert.equal(page.state.field(PlanKey.NAME), 'Park both arms');
});

// %% validation

const robotRun = (root) => byAction(root, PlanAction.RUN_ON_ROBOT)[0];
const validation = (root) => root.findAll((element) => element.className === 'step-validation').map((element) => element.textContent);

/**
 * Open a page whose plan parks the arms, picks an object up and places it.
 * @param {function(Object): void} prepare Prepares the fake API and storage.
 */
async function pickAndPlace(prepare = () => {}) {
  const opened = await openPage('', prepare);
  byAction(opened.root, PlanAction.ADD_OBJECT)[0].click();
  for (const action of ['park_arms', 'pick_up', 'place']) block(opened.root, action).click();
  return opened;
}

test('the run on the robot stays disabled until the plan passes its validation', async () => {
  const { root, api } = await pickAndPlace();
  assert.equal(robotRun(root).disabled, true);
  byAction(root, PlanAction.VALIDATE)[0].click();
  await settled();
  assert.equal(api.validated.length, 1);
  assert.equal(robotRun(root).disabled, false);
  assert.deepEqual(steps(root).map((card) => card.dataset.validation), [StepVerdict.VALID, StepVerdict.VALID, StepVerdict.VALID]);
  assert.match(message(root), /valid/);
  robotRun(root).click();
  await settled();
  assert.deepEqual([api.runs[0].mode, api.runs[0].overrideValidation], [RunMode.ROBOT, false]);
});

/**
 * @param {Object<string, string>} executors The executor of each run mode.
 * @returns {function(Object): void} Prepares the fake API to serve a profile of Tracy
 *   whose run modes execute so.
 */
const profileRunning = (executors) => ({ api }) => {
  api.catalogAnswer[PlanBuilderCatalogKey.PROFILE] = { [RobotProfileKey.ROBOT]: 'tracy', [RobotProfileKey.LABEL]: 'Tracy', [RobotProfileKey.EXECUTORS]: executors };
};

test('a profile running the robot run mode on the real robot marks it and offers it for a validated plan only', async () => {
  const { root, api } = await pickAndPlace(profileRunning({ [RunMode.ROBOT]: ExecutorKind.REAL }));
  assert.equal(robotRun(root).hidden, false);
  assert.match(robotRun(root).textContent, /real robot/);
  assert.equal(robotRun(root).classList.contains('real-robot'), true);
  assert.equal(robotRun(root).disabled, true);
  byAction(root, PlanAction.VALIDATE)[0].click();
  await settled();
  assert.equal(robotRun(root).disabled, false);
  robotRun(root).click();
  await settled();
  assert.deepEqual([api.runs[0].mode, api.runs[0].overrideValidation], [RunMode.ROBOT, false]);
  assert.match(message(root), /real robot/);
  assert.equal(robotRun(root).disabled, true);
});

test('developer mode does not let a plan run on the real robot without a passed validation', async () => {
  const { root, api } = await pickAndPlace((opened) => {
    profileRunning({ [RunMode.ROBOT]: ExecutorKind.REAL })(opened);
    opened.storage.setItem(DEVELOPER_MODE_KEY, String(true));
  });
  assert.equal(robotRun(root).disabled, true);
  assert.doesNotMatch(root.findAll((element) => element.className === 'validation-state')[0].textContent, /Developer mode/);
  byAction(root, PlanAction.VALIDATE)[0].click();
  await settled();
  robotRun(root).click();
  await settled();
  assert.deepEqual([api.runs[0].mode, api.runs[0].overrideValidation], [RunMode.ROBOT, false]);
});

test('a profile offering no run on the robot hides its button', async () => {
  const { root } = await pickAndPlace(profileRunning({ [RunMode.PERFORM]: ExecutorKind.KINEMATIC }));
  assert.equal(robotRun(root).hidden, true);
});

test('a pick out of reach fails its validation as unreachable and the robot run stays disabled', async () => {
  const { root } = await pickAndPlace(({ api }) => {
    api.validationAnswer = (planned) => planned.map((step, index) => ({
      [StepValidationKey.STEP]: step[PlanStepKey.IDENTIFIER],
      [StepValidationKey.VERDICT]: [StepVerdict.VALID, StepVerdict.FAILED, StepVerdict.UNCHECKED][index],
      ...(index === 1 ? { [StepValidationKey.REASON]: StepFailureReason.UNREACHABLE } : {}),
    }));
  });
  byAction(root, PlanAction.VALIDATE)[0].click();
  await settled();
  const failing = steps(root).filter((card) => card.dataset.validation === StepVerdict.FAILED);
  assert.equal(failing.length, 1);
  assert.equal(failing[0], steps(root)[1]);
  assert.match(validation(root)[1], new RegExp(REASON_TEXTS[StepFailureReason.UNREACHABLE]));
  assert.match(message(root), /step 2: unreachable/);
  assert.equal(robotRun(root).disabled, true);
});

test('an assumed step and the arm chosen automatically are shown on their steps', async () => {
  const { root } = await pickAndPlace(({ api }) => {
    api.validationAnswer = (planned) => planned.map((step, index) => ({
      [StepValidationKey.STEP]: step[PlanStepKey.IDENTIFIER],
      [StepValidationKey.VERDICT]: index === 0 ? StepVerdict.ASSUMED : StepVerdict.VALID,
      ...(index === 1 ? { [StepValidationKey.ARM]: 'right' } : {}),
    }));
  });
  byAction(root, PlanAction.VALIDATE)[0].click();
  await settled();
  assert.match(validation(root)[0], /Assumed/);
  assert.match(validation(root)[1], /Arm: right, chosen automatically/);
  assert.equal(robotRun(root).disabled, false);
  assert.match(message(root), /1 step is assumed/);
});

test('an edit of the plan or its scene invalidates the validation', async () => {
  const { root, page } = await pickAndPlace();
  byAction(root, PlanAction.VALIDATE)[0].click();
  await settled();
  const object = page.state.objects()[0][PlannedObjectKey.IDENTIFIER];
  page.placeObject(object, PlanPose.of(3, 3, 0, 0));
  assert.equal(robotRun(root).disabled, true);
  assert.deepEqual(steps(root).map((card) => card.dataset.validation), [undefined, undefined, undefined]);
  assert.match(root.findAll((element) => element.className === 'validation-state')[0].textContent, /Changed since its validation/);
});

test('a live object moved away from its pose in the plan invalidates the validation for good', async () => {
  const { root, page, live, timer } = await openPage();
  addMilk(root);
  for (const action of ['park_arms', 'pick_up', 'place']) block(root, action).click();
  const planned = page.state.objects()[0][PlannedObjectKey.POSE];
  const standing = structuredClone(live.world);
  standing.captured.objects['key-milk'] = structuredClone(planned);
  live.world = standing;
  byAction(root, PlanAction.VALIDATE)[0].click();
  await settled();
  byAction(root, PlanAction.STAGE)[0].click();
  await settled();
  await timer.tick();
  const validatedWhileLive = robotRun(root).disabled === false;
  const moved = structuredClone(standing);
  moved.captured.objects['key-milk'] = [planned[0] + 2 * SCENE_TOLERANCE, ...planned.slice(1)];
  live.world = moved;
  await timer.tickEvery(PollInterval.STATE);
  live.world = standing;
  await timer.tick();
  assert.equal(validatedWhileLive, true);
  assert.equal(robotRun(root).disabled, true);
  assert.deepEqual(steps(root).map((card) => card.dataset.validation), [undefined, undefined, undefined]);
  assert.match(root.findAll((element) => element.className === 'validation-state')[0].textContent, /scene changed since its validation/);
});

test('developer mode runs on the robot without a passed validation', async () => {
  const { root, api } = await openPage('', ({ api: fake }) => {
    fake.catalogAnswer[PlanBuilderCatalogKey.PROFILE] = SKILLED_PROFILE;
  }, { robot: false });
  byAction(root, PlanAction.ADD_SKILL)[0].click();
  assert.equal(robotRun(root).disabled, true);
  const developer = byAction(root, PlanAction.DEVELOPER_MODE)[0];
  developer.checked = true;
  developer.dispatch(DomEvent.CHANGE);
  assert.equal(robotRun(root).disabled, false);
  robotRun(root).click();
  await settled();
  assert.deepEqual([api.runs[0].mode, api.runs[0].overrideValidation], [RunMode.ROBOT, true]);
});

test('the physics run is an optional dry-run, not gated by the validation', async () => {
  const { root } = await pickAndPlace();
  const dryRun = byAction(root, PlanAction.SIMULATE)[0];
  assert.equal(dryRun.textContent, 'Dry-run in physics');
  assert.equal(dryRun.disabled, false);
});

// %% safety stops

/**
 * Open a page, dry-run a plan in physics and have a safety limit stop it.
 */
async function safetyStopped() {
  const opened = await openPage();
  const { root, api, timer } = opened;
  byAction(root, PlanAction.ADD_OBJECT)[0].click();
  block(root, 'park_arms').click();
  byAction(root, PlanAction.SIMULATE)[0].click();
  await settled();
  api.status = {
    [RunStatusKey.STATE]: RunState.SAFETY_STOPPED,
    [RunStatusKey.MODE]: RunMode.SIMULATE,
    [RunStatusKey.SAFETY_STOP]: { [SafetyStopKey.CONSTRAINT]: 'Left arm workspace', [SafetyStopKey.ACKNOWLEDGED]: false },
  };
  await timer.tick();
  return opened;
}

const banner = (root) => root.findAll((element) => element.className === 'safety-banner')[0];
const runButtons = (root) => [PlanAction.STAGE, PlanAction.PERFORM, PlanAction.SIMULATE, PlanAction.VALIDATE, PlanAction.RUN_ON_ROBOT].map((action) => byAction(root, action)[0]);

test('a safety stop shows its banner and blocks every run until it is acknowledged', async () => {
  const { root, api } = await safetyStopped();
  assert.equal(banner(root).hidden, false);
  const shown = root.findAll((element) => element.className === 'safety-message')[0].textContent;
  assert.equal(shown, new SafetyStopBanner().message(api.status));
  assert.ok(runButtons(root).every((button) => button.disabled));
  assert.equal(byAction(root, PlanAction.ACKNOWLEDGE_STOP)[0].hidden, false);
  assert.equal(byAction(root, PlanAction.RESTART_PLAN)[0].hidden, true);
  assert.equal(api.runs.length, 1);
});

test('an acknowledged safety stop restarts the plan from its beginning', async () => {
  const { root, api } = await safetyStopped();
  byAction(root, PlanAction.ACKNOWLEDGE_STOP)[0].click();
  await settled();
  assert.equal(api.acknowledged, 1);
  assert.equal(byAction(root, PlanAction.RESTART_PLAN)[0].hidden, false);
  assert.equal(byAction(root, PlanAction.SIMULATE)[0].disabled, false);
  byAction(root, PlanAction.RESTART_PLAN)[0].click();
  await settled();
  assert.deepEqual(api.runs.map((run) => run.mode), [RunMode.SIMULATE, RunMode.SIMULATE]);
  assert.deepEqual(api.runs[1].plan, api.runs[0].plan);
  assert.equal(banner(root).hidden, true);
});

test('an acknowledged safety stop can be aborted without running again', async () => {
  const { root, api } = await safetyStopped();
  byAction(root, PlanAction.ACKNOWLEDGE_STOP)[0].click();
  await settled();
  byAction(root, PlanAction.ABORT_PLAN)[0].click();
  await settled();
  assert.equal(banner(root).hidden, true);
  assert.equal(api.runs.length, 1);
  assert.equal(byAction(root, PlanAction.SIMULATE)[0].disabled, false);
});

// %% run view

const runView = (root) => root.findAll((element) => element.className === 'run-view')[0];

test('a performing run shows the run view in place of the steps until the person edits again', async () => {
  const { root, api } = await safetyStopped();
  const [step] = api.runs[0].plan[PlanKey.ROBOTS][0][PlannedRobotKey.STEPS];
  const identifier = step[PlanStepKey.IDENTIFIER];
  api.status = {
    ...api.status,
    [RunStatusKey.EVENTS]: [
      { [RunEventKey.KIND]: RunEventKind.STEP, [RunEventKey.STEP]: identifier, [RunEventKey.STATE]: StepState.PENDING },
      { [RunEventKey.KIND]: RunEventKind.STEP, [RunEventKey.STEP]: identifier, [RunEventKey.STATE]: StepState.FAILED, [RunEventKey.ATTEMPT]: 1, [RunEventKey.ATTEMPTS]: 3, [RunEventKey.REASON]: 'Left arm workspace' },
      { [RunEventKey.KIND]: RunEventKind.SAFETY_STOP, [RunEventKey.STEP]: identifier, [RunEventKey.CONSTRAINT]: 'Left arm workspace' },
    ],
  };
  byAction(root, PlanAction.ACKNOWLEDGE_STOP)[0].click();
  await settled();
  assert.equal(runView(root).hidden, false);
  assert.equal(banner(root).hidden, false);
  const [shown] = runView(root).findAll((element) => element.className === 'run-step');
  assert.equal(shown.dataset.state, StepState.FAILED);
  assert.match(runView(root).innerText, /Stopped by a safety limit in 1\. /);
  byAction(root, PlanAction.TOGGLE_RUN)[0].click();
  assert.equal(runView(root).hidden, true);
  assert.equal(byAction(root, PlanAction.TOGGLE_RUN)[0].hidden, false);
});

test('a staged live scene keeps the editable steps', async () => {
  const { root } = await openPage();
  byAction(root, PlanAction.STAGE)[0].click();
  await settled();
  assert.equal(runView(root).hidden, true);
});

// %% placing

const ZONED_PROFILE = {
  [RobotProfileKey.ROBOT]: 'tracy',
  [RobotProfileKey.LABEL]: 'Tracy',
  [RobotProfileKey.ZONES]: [
    { [ZoneKey.IDENTIFIER]: 'left_tray', [ZoneKey.LABEL]: 'Left tray', [ZoneKey.AREA]: { minX: 0.6, maxX: 0.8, minY: 0.3, maxY: 0.5 } },
    { [ZoneKey.IDENTIFIER]: 'center', [ZoneKey.LABEL]: 'Center', [ZoneKey.AREA]: { minX: 0.6, maxX: 0.8, minY: -0.1, maxY: 0.1 } },
  ],
};

/**
 * Open a page of Tracy's zoned profile whose plan picks the first of two objects and
 * places it.
 */
async function tracyPlacing() {
  const opened = await openPage('', ({ api }) => {
    api.catalogAnswer[PlanBuilderCatalogKey.PROFILE] = ZONED_PROFILE;
  }, { robot: false });
  await settled();
  byAction(opened.root, PlanAction.ADD_OBJECT)[0].click();
  byAction(opened.root, PlanAction.ADD_OBJECT)[0].click();
  for (const action of ['pick_up', 'place']) block(opened.root, action).click();
  const place = opened.page.state.steps()[1];
  const choose = (mode) => {
    const select = parameter(opened.root, 'target_location');
    select.value = mode;
    select.dispatch(DomEvent.CHANGE);
  };
  return { ...opened, place: place[PlanStepKey.IDENTIFIER], choose };
}

const target = (page, identifier) => page.state.step(identifier)[PlanStepKey.VALUES].target_location;
const markerInput = (root, axis) => root.findAll((element) => element.dataset.marker === 'true')[0].findAll((element) => element.dataset.field === axis)[0];

test('the reach of the edited robot is asked once and the profile zones lie on its table', async () => {
  const { api, page, scene } = await tracyPlacing();
  assert.equal(page.state.activeRobot()[PlannedRobotKey.MODEL], 'tracy');
  assert.deepEqual(api.reached, ['tracy']);
  assert.deepEqual(scene().shown.overlay.zones.map((zone) => zone.identifier), ['left_tray', 'center']);
});

test('a place step goes into a zone or on top of another object', async () => {
  const { root, page, place, choose } = await tracyPlacing();
  const modes = parameter(root, 'target_location').children.map((option) => option.value);
  assert.ok([PlacementMode.ZONE, PlacementMode.ON_TOP_OF, PlacementMode.MARKER].every((mode) => modes.includes(mode)));
  choose(PlacementMode.ZONE);
  assert.equal(target(page, place)[DestinationKey.PLACEMENT], PlacementMode.ZONE);
  assert.equal(target(page, place)[DestinationKey.ZONE], 'left_tray');
  const zone = parameter(root, DestinationKey.ZONE);
  zone.value = 'center';
  zone.dispatch(DomEvent.CHANGE);
  assert.equal(target(page, place)[DestinationKey.ZONE], 'center');
  choose(PlacementMode.ON_TOP_OF);
  const [placed, other] = page.state.objects().map((item) => item[PlannedObjectKey.IDENTIFIER]);
  assert.equal(page.state.stepObject(page.state.step(place)), placed);
  assert.equal(target(page, place)[DestinationKey.OBJECT], other);
  assert.deepEqual(parameter(root, DestinationKey.OBJECT).children.map((option) => option.value), [other]);
  assert.deepEqual(page.state.problems(page.state.step(place)), []);
});

test('dragging the marker updates its numeric fields and editing them moves the marker', async () => {
  const { root, page, place, choose, scene } = await tracyPlacing();
  choose(PlacementMode.MARKER);
  const selection = new Selection(MarkerKind.TARGET, place, 'target_location');
  const dragged = [0.7, -0.2, 1.3, 0, 0, Math.sin(0.5), Math.cos(0.5)];
  const moving = scene().listeners.onMove(selection, dragged);
  assert.deepEqual(PlanPose.position(moving.pose), [0.7, -0.2, 0.88]);
  assert.equal(moving.reachable, true);
  scene().listeners.onPlace(selection, dragged);
  assert.equal(markerInput(root, 'x').value, '0.7');
  assert.equal(markerInput(root, 'y').value, '-0.2');
  assert.equal(markerInput(root, 'yaw°').value, String(PlanPose.degrees(1)));
  const x = markerInput(root, 'x');
  x.value = '0.5';
  x.dispatch(DomEvent.CHANGE);
  const shown = scene().shown.document[PlanKey.ROBOTS][0][PlannedRobotKey.STEPS][1][PlanStepKey.VALUES].target_location;
  assert.equal(shown[DestinationKey.PLACEMENT], PlacementMode.MARKER);
  assert.deepEqual(PlanPose.position(shown[DestinationKey.POSE]), [0.5, -0.2, 0.88]);
  assert.ok(Math.abs(PlanPose.yaw(shown[DestinationKey.POSE]) - 1) < 1e-9);
});

test('a marker dragged out of reach turns red and stays red where it is put down', async () => {
  const { page, place, choose, scene } = await tracyPlacing();
  choose(PlacementMode.MARKER);
  const selection = new Selection(MarkerKind.TARGET, place, 'target_location');
  assert.equal(scene().shown.overlay.reachable.get(selection.key), true);
  const beyond = PlanPose.of(1.5, 0.1, 0.9, 0);
  const moving = scene().listeners.onMove(selection, beyond);
  assert.equal(moving.reachable, false);
  assert.deepEqual(PlanPose.position(moving.pose), [1.5, 0.1, 0]);
  scene().listeners.onPlace(selection, beyond);
  assert.deepEqual(PlanPose.position(target(page, place)[DestinationKey.POSE]), [1.5, 0.1, 0]);
  assert.equal(scene().shown.overlay.reachable.get(selection.key), false);
});

test('a detect step looks in a zone or around a marker', async () => {
  const { root, page } = await openPage('', ({ api }) => {
    api.catalogAnswer[PlanBuilderCatalogKey.PROFILE] = ZONED_PROFILE;
  }, { robot: false });
  await settled();
  byAction(root, PlanAction.ADD_OBJECT)[0].click();
  block(root, 'detect').click();
  const detect = page.state.steps()[0][PlanStepKey.IDENTIFIER];
  const region = parameter(root, 'region');
  region.value = RegionKind.ZONE;
  region.dispatch(DomEvent.CHANGE);
  assert.deepEqual(page.state.step(detect)[PlanStepKey.VALUES].region, { [DetectionRegionKey.KIND]: RegionKind.ZONE, [DetectionRegionKey.ZONE]: 'left_tray' });
  const kind = parameter(root, 'region');
  kind.value = RegionKind.MARKER;
  kind.dispatch(DomEvent.CHANGE);
  const marker = page.state.step(detect)[PlanStepKey.VALUES].region;
  assert.equal(marker[DetectionRegionKey.KIND], RegionKind.MARKER);
  assert.equal(PlanPose.position(marker[DetectionRegionKey.POSE])[2], 0.88);
  assert.deepEqual(page.state.targets(page.state.step(detect)).map((found) => found.marker), [true]);
});

// %% waiting and failing

/**
 * @returns {{promise: Promise<*>, resolve: function(*): void, reject: function(*): void}}
 *   An answer the test gives when it chooses.
 */
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolving, rejecting) => {
    resolve = resolving;
    reject = rejecting;
  });
  return { promise, resolve, reject };
}

const validateButton = (root) => byAction(root, PlanAction.VALIDATE)[0];
const scanButton = (root) => byAction(root, PlanAction.SCAN_SCENE)[0];

test('a validation that has not answered yet cannot be started twice, nor a scan or a run beside it', async () => {
  const { root, api } = await pickAndPlace();
  const answer = deferred();
  const validate = api.validate.bind(api);
  api.validate = (plan) => {
    api.validated.push(plan);
    return answer.promise.then(() => validate(plan));
  };
  validateButton(root).click();
  await settled();
  validateButton(root).click();
  await settled();
  assert.equal(api.validated.length, 1);
  assert.equal(validateButton(root).disabled, true);
  assert.equal(scanButton(root).disabled, true);
  assert.equal(robotRun(root).disabled, true);
  answer.resolve();
  await settled();
  await settled();
  assert.equal(validateButton(root).disabled, false);
  assert.equal(scanButton(root).disabled, false);
  assert.equal(robotRun(root).disabled, false);
});

test('while a plan runs only Stop is offered, so nothing replaces the run or validates beside it', async () => {
  const { root, api, timer } = await pickAndPlace(profileRunning({ [RunMode.ROBOT]: ExecutorKind.REAL }));
  validateButton(root).click();
  await settled();
  robotRun(root).click();
  await settled();
  await timer.tick();
  assert.deepEqual(runButtons(root).map((button) => button.disabled), [true, true, true, true, true]);
  assert.equal(scanButton(root).disabled, true);
  assert.equal(byAction(root, PlanAction.STOP)[0].disabled, false);
  api.status = { ...api.status, [RunStatusKey.STATE]: RunState.FINISHED };
  await timer.tick();
  assert.equal(validateButton(root).disabled, false);
  assert.equal(scanButton(root).disabled, false);
});

test('while the run\'s record is saved the page says so, offers only Stop and shows a failed save', async () => {
  const { root, api, timer } = await pickAndPlace(profileRunning({ [RunMode.ROBOT]: ExecutorKind.REAL }));
  validateButton(root).click();
  await settled();
  robotRun(root).click();
  await settled();
  api.status = { ...api.status, [RunStatusKey.STATE]: RunState.SAVING };
  await timer.tick();
  const runState = root.findAll((element) => element.className === 'run-state')[0];
  assert.match(runState.textContent, /saving the run's record/i);
  assert.match(runState.textContent, /robot holds/);
  assert.deepEqual(runButtons(root).map((button) => button.disabled), [true, true, true, true, true]);
  assert.equal(scanButton(root).disabled, true);
  assert.equal(byAction(root, PlanAction.STOP)[0].disabled, false);
  api.status = { ...api.status, [RunStatusKey.STATE]: RunState.SAVE_FAILED };
  await timer.tick();
  assert.match(runState.textContent, /saving its record failed/);
  assert.equal(validateButton(root).disabled, false);
});

test('stopping says so until the run ended, and a stop that fails says why', async () => {
  const { root, api } = await openPage();
  byAction(root, PlanAction.SIMULATE)[0].click();
  await settled();
  const answer = deferred();
  const stop = api.stop.bind(api);
  api.stop = () => answer.promise.then(() => stop());
  const stopButton = byAction(root, PlanAction.STOP)[0];
  stopButton.click();
  await settled();
  assert.match(message(root), /Stopping/);
  assert.equal(stopButton.disabled, true);
  answer.resolve();
  await settled();
  await settled();
  assert.match(message(root), /stopped/);

  api.status = { ...api.status, [RunStatusKey.STATE]: RunState.RUNNING };
  api.stop = async () => {
    throw new Error('Failed to fetch');
  };
  byAction(root, PlanAction.SIMULATE)[0].click();
  await settled();
  byAction(root, PlanAction.STOP)[0].click();
  await settled();
  assert.match(message(root), /could not be stopped.*Failed to fetch/);
  assert.equal(byAction(root, PlanAction.STOP)[0].disabled, false);
});

test('a plan builder that stops answering is shown until it answers again', async () => {
  const { root, api, timer } = await openPage();
  byAction(root, PlanAction.SIMULATE)[0].click();
  await settled();
  const runStatus = api.runStatus.bind(api);
  api.runStatus = async () => {
    throw new TypeError('Failed to fetch');
  };
  await timer.tick();
  const runState = () => root.findAll((element) => element.className === 'run-state')[0].textContent;
  assert.match(runState(), /plan builder does not answer.*Failed to fetch/);
  api.runStatus = runStatus;
  await timer.tick();
  assert.match(runState(), /^The demo runs\./);
  assert.doesNotMatch(runState(), /does not answer/);
});

test('a run on the real robot restarts after its safety stop only once the plan passed a new validation', async () => {
  const { root, api, timer } = await pickAndPlace(profileRunning({ [RunMode.ROBOT]: ExecutorKind.REAL }));
  validateButton(root).click();
  await settled();
  robotRun(root).click();
  await settled();
  api.status = {
    [RunStatusKey.STATE]: RunState.SAFETY_STOPPED,
    [RunStatusKey.MODE]: RunMode.ROBOT,
    [RunStatusKey.SAFETY_STOP]: { [SafetyStopKey.CONSTRAINT]: 'Left arm workspace', [SafetyStopKey.ACKNOWLEDGED]: false },
  };
  await timer.tick();
  byAction(root, PlanAction.ACKNOWLEDGE_STOP)[0].click();
  await settled();
  const restart = () => byAction(root, PlanAction.RESTART_PLAN)[0];
  assert.equal(restart().disabled, true);
  assert.match(root.findAll((element) => element.className === 'safety-message')[0].textContent, /Validate the plan again/);
  validateButton(root).click();
  await settled();
  await settled();
  assert.equal(restart().disabled, false);
  restart().click();
  await settled();
  assert.deepEqual(api.runs.map((run) => [run.mode, run.overrideValidation]), [[RunMode.ROBOT, false], [RunMode.ROBOT, false]]);
});

test('a validation or scan without an answer says which request got none, a refusal says why', async () => {
  const { root, api } = await pickAndPlace();
  api.validate = async () => {
    throw new TypeError('Failed to fetch');
  };
  validateButton(root).click();
  await settled();
  await settled();
  assert.match(message(root), /^The validation got no answer from the plan builder \(Failed to fetch\)/);
  api.scan = async () => {
    throw new TypeError('NetworkError when attempting to fetch resource.');
  };
  scanButton(root).click();
  await settled();
  await settled();
  assert.match(message(root), /^The scan got no answer from the plan builder \(NetworkError/);
  api.validate = async () => {
    throw new RequestRefused(500, 'The plan could not be validated: RoboKudo did not answer within 30 s');
  };
  validateButton(root).click();
  await settled();
  await settled();
  assert.equal(message(root), 'The plan could not be validated: RoboKudo did not answer within 30 s');
});
