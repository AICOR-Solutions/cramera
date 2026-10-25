/**
 * The builder page: lays out the plan's robots, actions, objects and constraints, the
 * steps, the 3D view and the demo controls, and connects them to the plan, the plan
 * builder's routes and the live publisher a started demo publishes on.
 */

import {
  DemoSourceKey,
  IndexEntryKey,
  LoadedEnvironmentKey,
  UrdfFolderKey,
  ObjectPosesKey,
  LiveInfoKey,
  LivePlanNodeKey,
  PlanBuilderCatalogKey,
  PlanBuilderPageParameter,
  PlanKey,
  PlannedObjectKey,
  PlannedRobotKey,
  PlanRecordKey,
  PlanStepKey,
  PlanSummaryKey,
  RobotInstanceKey,
  RunMode,
  RunState,
  RunStatusKey,
  SavedDemoKey,
  StepConstraintKey,
  ConstraintObservationKey,
  ConstraintTextKey,
  SurfaceKey,
  SurfacesKey,
} from '../../../protocol.js';
import { PageStatus } from '../../../core/page-status.js';
import { ConstraintSentences, ConstraintsView } from './constraints-view.js';
import { Elements, PlanAction } from './elements.js';
import { LiveNames } from './live-client.js';
import { ObjectsView } from './objects-view.js';
import { MarkerKind, PlanSceneListeners, Selection, TransformMode } from './plan-scene.js';
import { PlanRefused, PlanState } from './plan-state.js';
import { PlanPose, PoseIndex } from './poses.js';
import { EnvironmentView, RobotsView } from './robots-view.js';
import { StepsView } from './steps-view.js';

/**
 * How often a started demo and its live world are asked for their state, in
 * milliseconds.
 */
export const POLL_INTERVAL = 1000;

/**
 * The storage key of the robot model the person used last, which a new plan starts with.
 */
export const ROBOT_MODEL_KEY = 'cramera.plan-builder.robot-model';

/**
 * The storage key of the folder the URDF picker showed last, which it opens on again.
 */
export const URDF_FOLDER_KEY = 'cramera.plan-builder.urdf-folder';

/**
 * The choice of the saved plans' select that opens none.
 */
const OPEN_PROMPT = Object.freeze({ value: '', label: 'Open a saved plan…' });

/**
 * How people read each state of the demo process.
 */
const RUN_LABELS = Object.freeze({
  [RunState.IDLE]: 'No demo runs.',
  [RunState.RUNNING]: 'The demo runs.',
  [RunState.FINISHED]: 'The demo finished.',
  [RunState.FAILED]: 'The demo failed; its output is below.',
  [RunState.STOPPED]: 'The demo was stopped.',
});

/**
 * The run states in which the live world is published.
 */
const LIVE_STATES = Object.freeze([RunState.RUNNING]);

/**
 * How many missing meshes a loaded environment's message names.
 */
export const NAMED_MISSING_MESHES = 3;

/**
 * @param {string} label The loaded environment's name for people.
 * @param {Array<string>} missing The mesh references that resolved to no file.
 * @returns {string} What the page says about the loaded environment.
 */
export function loadedMessage(label, missing) {
  if (missing.length === 0) return `Loaded ${label}.`;
  const named = missing.slice(0, NAMED_MISSING_MESHES).join(', ');
  const more = missing.length > NAMED_MISSING_MESHES ? ', …' : '';
  const count = missing.length === 1 ? '1 mesh it names was' : `${missing.length} meshes it names were`;
  return `Loaded ${label}; ${count} not found and left out: ${named}${more}`;
}

// %% environment

/**
 * What the page needs of the browser.
 */
export class BuilderEnvironment {
  /**
   * @param {Object} parts The parts, by name: `document`, `api` (a `PlanBuilderApi`),
   *   `live` (makes a `LiveClient` for a base URL), `storage` (a `Storage`), `query`
   *   (the page's `URLSearchParams`), `createScene` (builds a `PlanScene` in a container
   *   with listeners, or null without WebGL) and `timer` (`repeat(callback, interval)`
   *   answering a handle, `cancel(handle)`).
   */
  constructor(parts) {
    /**
     * The page's document.
     * @type {Document}
     */
    this.document = parts.document;
    /**
     * The plan builder's routes.
     * @type {import('./builder-api.js').PlanBuilderApi}
     */
    this.api = parts.api;
    /**
     * Makes the client of a live publisher.
     * @type {function(string): import('./live-client.js').LiveClient}
     */
    this.live = parts.live;
    /**
     * The browser's storage.
     * @type {Storage}
     */
    this.storage = parts.storage;
    /**
     * The page's query parameters.
     * @type {URLSearchParams}
     */
    this.query = parts.query;
    /**
     * Builds the 3D view, or null when the browser cannot show one.
     * @type {(function(HTMLElement, PlanSceneListeners): import('./plan-scene.js').PlanScene)|null}
     */
    this.createScene = parts.createScene;
    /**
     * Calls a callback repeatedly.
     * @type {{repeat: function(function(): void, number): *, cancel: function(*): void}}
     */
    this.timer = parts.timer;
  }
}

// %% page

export class BuilderPage {
  /**
   * What the page needs of the browser.
   * @type {BuilderEnvironment}
   */
  #environment;

  /**
   * Builds the page's frame and owns its listeners.
   * @type {Elements}
   */
  #elements;

  /**
   * The plan, once the catalog arrived.
   * @type {PlanState|null}
   */
  state = null;

  /**
   * The identity of the saved plan being edited, or null for a new plan.
   * @type {string|null}
   */
  #planIdentifier = null;

  /**
   * The page's parts.
   * @type {Object}
   */
  #parts = {};

  /**
   * The 3D view, or null without WebGL.
   * @type {import('./plan-scene.js').PlanScene|null}
   */
  #scene = null;

  /**
   * The environment the 3D view shows.
   * @type {string|null|undefined}
   */
  #shownEnvironment = undefined;

  /**
   * The live publisher started demos publish on.
   * @type {import('./live-client.js').LiveClient|null}
   */
  #live = null;

  /**
   * The demo process's last status.
   * @type {Object}
   */
  #run = { [RunStatusKey.STATE]: RunState.IDLE };

  /**
   * What the live world showed last: its object keys, poses and plan statuses.
   * @type {{keys: Map<string, string>, objects: Map<string, Array<number>>, robots: Map<string, Object>, statuses: Array<string|null>, surfaces: Map<string, Array<string>>, published: boolean}}
   */
  #world = PageWorld.empty();

  /**
   * The constraint requests sent to the live plan, by node and text.
   * @type {Set<string>}
   */
  #attached = new Set();

  /**
   * The handle of the polling, or null.
   * @type {*}
   */
  #polling = null;

  /**
   * Whether a poll is answered right now, so polls do not pile up.
   * @type {boolean}
   */
  #polled = false;

  /**
   * How far the page is, for people and for tools such as the screenshot command.
   * @type {PageStatus}
   */
  #pageStatus;

  /**
   * The page's root element.
   * @type {HTMLElement}
   */
  #root;

  /**
   * @param {HTMLElement} root The page's root element.
   * @param {BuilderEnvironment} environment What the page needs of the browser.
   */
  constructor(root, environment) {
    this.#root = root;
    this.#environment = environment;
    this.#elements = new Elements(environment.document);
  }

  /**
   * Load the catalog and the plan the query names, or start a new plan.
   * @returns {Promise<void>} Settles once the page shows the plan.
   */
  async start() {
    const elements = this.#elements;
    const statusLine = elements.create('p', 'status-line');
    this.#pageStatus = new PageStatus(this.#environment.document.documentElement, statusLine);
    this.#pageStatus.loading('Loading the catalog…');
    const catalog = await this.#environment.api.catalog();
    this.#live = this.#environment.live(catalog[PlanBuilderCatalogKey.LIVE_URL]);
    const query = this.#environment.query;
    const environments = catalog[PlanBuilderCatalogKey.ENVIRONMENTS].map((entry) => entry[IndexEntryKey.NAME]);
    const asked = query.get(PlanBuilderPageParameter.ENVIRONMENT);
    const environment = environments.includes(asked) ? asked : (environments[0] ?? null);
    this.state = PlanState.empty(catalog, environment, this.#environment.storage.getItem(ROBOT_MODEL_KEY));
    this.#layout(statusLine);
    const saved = query.get(PlanBuilderPageParameter.PLAN);
    if (saved) await this.#open(saved);
    this.render();
    const missing = catalog[PlanBuilderCatalogKey.MISSING];
    this.#pageStatus.ready(missing.length ? `The CRAM workspace is not importable here (missing ${missing.join(', ')}); plans can be composed and saved, not run.` : 'Compose the plan, then start the live scene or run it.');
    this.#polling = this.#environment.timer.repeat(() => this.#poll(), POLL_INTERVAL);
  }

  /**
   * Show the plan in every part.
   */
  render() {
    const state = this.state;
    const parts = this.#parts;
    parts.name.value = state.field(PlanKey.NAME);
    parts.task.value = state.field(PlanKey.TASK);
    parts.environment.render();
    this.#elements.options(parts.saved, this.#planChoices(), OPEN_PROMPT.value);
    parts.robots.render();
    parts.steps.render(this.#world.statuses, this.#world.observations);
    parts.objects.render(this.#selection()?.kind === MarkerKind.OBJECT ? this.#selection().identifier : null);
    parts.constraints.render();
    const robot = state.activeRobot();
    parts.planTitle.textContent = `Plan of ${robot?.[PlannedRobotKey.LABEL] ?? 'no robot'}`;
    if (robot) this.#environment.storage.setItem(ROBOT_MODEL_KEY, robot[PlannedRobotKey.MODEL]);
    this.#showRun();
    this.#showScene();
  }

  // %% editing

  /**
   * Apply a change of the plan and show it; a change the plan refuses is reported.
   * @param {function(): *} change The change.
   */
  edit(change) {
    // the boundary where an edit the plan refuses becomes a message for the person
    try {
      change();
    } catch (error) {
      if (!(error instanceof PlanRefused)) throw error;
      this.report(error.message);
    }
    this.render();
  }

  /**
   * Write a URDF of the viewer's machine as an environment and start the plan there.
   * @param {string} path The URDF or xacro file.
   * @returns {Promise<void>} Settles once the environment is chosen or refused.
   */
  async loadEnvironment(path) {
    this.report(`Loading ${path}…`);
    const loaded = await this.#environment.api.loadEnvironment(path).catch((error) => {
      this.report(error.message);
      return null;
    });
    if (!loaded) return;
    const entry = loaded[LoadedEnvironmentKey.ENTRY];
    this.state.catalog[PlanBuilderCatalogKey.ENVIRONMENTS].push(entry);
    this.edit(() => this.state.setField(PlanKey.ENVIRONMENT, entry[IndexEntryKey.NAME]));
    this.report(loadedMessage(entry[IndexEntryKey.ENVIRONMENT] ?? entry[IndexEntryKey.NAME], loaded[LoadedEnvironmentKey.MISSING_MESHES]));
  }

  /**
   * @param {string|null} path A folder of the viewer's machine, or null for the one the
   *   picker showed last, else the home folder.
   * @returns {Promise<Object|null>} The `UrdfFolder`, or null once the refusal is
   *   reported.
   */
  async listFolder(path) {
    const storage = this.#environment.storage;
    const remembered = path === null ? storage.getItem(URDF_FOLDER_KEY) : null;
    const api = this.#environment.api;
    // a remembered folder that is gone opens the home folder instead
    const listing = remembered === null ? api.urdfFolder(path) : api.urdfFolder(remembered).catch(() => api.urdfFolder(null));
    const folder = await listing.catch((error) => {
      this.report(error.message);
      return null;
    });
    if (folder) storage.setItem(URDF_FOLDER_KEY, folder[UrdfFolderKey.PATH]);
    return folder;
  }

  /**
   * @param {string} message What the person should know.
   */
  report(message) {
    this.#parts.message.textContent = message;
  }

  /**
   * @param {{object: string}} selection The object picked in a list.
   */
  select(selection) {
    const picked = new Selection(MarkerKind.OBJECT, selection.object);
    this.#parts.selection = picked;
    this.#scene?.select(picked);
    this.render();
  }

  /**
   * @param {string} text A sentence.
   * @returns {Promise<Object|null>} The sentence compiled without a step, or null when
   *   it was refused.
   */
  async compileSentence(text) {
    return this.#environment.api.compile({ [ConstraintTextKey.TEXT]: text }).catch((error) => {
      this.report(error.message);
      return null;
    });
  }

  /**
   * Compile a sentence for a step of the edited robot and attach it.
   * @param {string} identifier The step.
   * @param {string} text The sentence.
   * @returns {Promise<void>} Settles once it is attached or refused.
   */
  async attachConstraint(identifier, text) {
    const step = this.state.step(identifier);
    const request = {
      [ConstraintTextKey.TEXT]: text,
      [ConstraintTextKey.STEP_ACTION]: step[PlanStepKey.ACTION],
      [ConstraintTextKey.OBJECTS]: this.state.objects().map((item) => item[PlannedObjectKey.IDENTIFIER]),
    };
    const subject = this.state.stepObject(step);
    if (subject !== undefined) request[ConstraintTextKey.STEP_OBJECT] = subject;
    const compiled = await this.#environment.api.compile(request).catch((error) => {
      this.report(error.message);
      return null;
    });
    if (!compiled) return;
    if (!compiled[StepConstraintKey.MONITOR_TYPE]) {
      this.report(`No rule reads “${text}”; it is not attached.`);
      return;
    }
    this.edit(() => {
      if (!this.state.attachConstraint(identifier, compiled)) this.report('The step holds that constraint already.');
      else this.report(`Attached “${text}” as ${compiled[StepConstraintKey.SWITCH] ?? compiled[StepConstraintKey.MONITOR_TYPE]}.`);
    });
  }

  /**
   * Take the performing robot's pose in the live world as a pose field's value.
   * @param {string} identifier The step.
   * @param {string} field The pose field.
   */
  useLivePose(identifier, field) {
    const robot = this.#world.robots.get(this.state.activeRobot()[PlannedRobotKey.IDENTIFIER]);
    if (!robot) {
      this.report('Start the live scene to take the robot’s pose from it.');
      return;
    }
    this.edit(() => this.state.setTarget(identifier, field, robot[RobotInstanceKey.POSE].map(PlanPose.rounded)));
  }

  /**
   * @returns {Map<string, Array<string>>} The live world's annotated surface names by
   *   their annotation's class name.
   */
  surfaces() {
    return this.#world.surfaces;
  }

  // %% plans

  /**
   * Start a new plan in the shown environment.
   */
  #newPlan() {
    this.#planIdentifier = null;
    this.state = PlanState.empty(this.state.catalog, this.state.field(PlanKey.ENVIRONMENT) || null, this.#environment.storage.getItem(ROBOT_MODEL_KEY));
    this.report('New plan.');
    this.render();
  }

  /**
   * @param {string} identifier A saved plan's identity.
   * @returns {Promise<void>} Settles once the plan is shown or refused.
   */
  async #open(identifier) {
    const record = await this.#environment.api.plan(identifier).catch((error) => {
      this.report(error.message);
      return null;
    });
    if (!record) return;
    this.#planIdentifier = record[PlanRecordKey.IDENTIFIER];
    this.state = new PlanState(this.state.catalog, record[PlanRecordKey.DOCUMENT]);
  }

  /**
   * Save the plan, under its identity once it has one.
   * @returns {Promise<void>} Settles once it is saved or refused.
   */
  async #save() {
    const saved = await this.#environment.api.save(this.state.document, this.#planIdentifier).catch((error) => {
      this.report(error.message);
      return null;
    });
    if (!saved) return;
    this.#planIdentifier = saved[PlanRecordKey.IDENTIFIER];
    const plans = await this.#environment.api.plans();
    this.state.catalog[PlanBuilderCatalogKey.PLANS] = plans[PlanBuilderCatalogKey.PLANS];
    this.report(`Saved ${this.state.field(PlanKey.NAME)}.`);
    this.render();
  }

  // %% demos

  /**
   * Show the demo generated from the plan.
   * @returns {Promise<void>} Settles once it is shown or refused.
   */
  async #showDemo() {
    const demo = await this.#environment.api.demo(this.state.document).catch((error) => {
      this.report(error.message);
      return null;
    });
    if (!demo) return;
    this.#parts.output.textContent = demo[DemoSourceKey.SOURCE];
    this.#parts.output.hidden = false;
    this.report(`Generated ${demo[DemoSourceKey.FILE_NAME]}.`);
  }

  /**
   * Write the demo into the output directory.
   * @returns {Promise<void>} Settles once it is written or refused.
   */
  async #writeDemo() {
    const saved = await this.#environment.api.writeDemo(this.state.document).catch((error) => {
      this.report(error.message);
      return null;
    });
    if (saved) this.report(`Wrote ${saved[SavedDemoKey.PATH]}; run it with: ${saved[SavedDemoKey.COMMAND]}`);
  }

  /**
   * @param {string} mode A `RunMode` value.
   * @returns {Promise<void>} Settles once the demo started or was refused.
   */
  async #start(mode) {
    const status = await this.#environment.api.run(this.state.document, mode).catch((error) => {
      this.report(error.message);
      return null;
    });
    if (!status) return;
    this.#world = PageWorld.empty();
    this.#attached.clear();
    this.#run = status;
    this.report(mode === RunMode.STAGE ? 'Starting the live scene; building the world takes a while.' : 'Running the plan; watch it in the 3D view or the viewer.');
    this.render();
  }

  /**
   * @returns {Promise<void>} Settles once the demo stopped.
   */
  async #stop() {
    this.#run = await this.#environment.api.stop();
    this.#world = PageWorld.empty();
    this.render();
  }

  /**
   * Write the live world's object and robot poses into the plan.
   */
  #capture() {
    if (!this.#world.published) {
      this.report('Start the live scene to capture poses from it.');
      return;
    }
    this.edit(() => {
      for (const [identifier, pose] of this.#world.objects) this.state.setObjectPose(identifier, pose.map(PlanPose.rounded));
      for (const [identifier, robot] of this.#world.robots) {
        this.state.setRobotPose(identifier, robot[RobotInstanceKey.POSE].map(PlanPose.rounded));
        this.state.setRobotPosture(identifier, robot[RobotInstanceKey.JOINT_POSITIONS] ?? {});
      }
      this.report('Captured the live poses into the plan.');
    });
  }

  // %% live world

  /**
   * Ask the demo process and, while it runs, its live world for their state.
   * @returns {Promise<void>} Settles once both answered.
   */
  async #poll() {
    if (this.#polled || !this.state) return;
    this.#polled = true;
    const run = await this.#environment.api.runStatus().catch(() => this.#run);
    const before = this.#run[RunStatusKey.STATE];
    this.#run = run;
    const world = LIVE_STATES.includes(run[RunStatusKey.STATE]) ? await this.#readWorld().catch(() => PageWorld.empty()) : PageWorld.empty();
    const changed = before !== run[RunStatusKey.STATE] || world.published !== this.#world.published || world.signature() !== this.#world.signature();
    this.#world = world;
    this.#polled = false;
    if (changed) this.render();
    else {
      this.#showRun();
      this.#showScene();
    }
  }

  /**
   * @returns {Promise<PageWorld>} What the live world shows, its constraints sent once
   *   the performing robot's plan is published.
   */
  async #readWorld() {
    const live = this.#live;
    const info = await live.info();
    if (!info[LiveInfoKey.RUNNING]) return PageWorld.empty();
    const [catalog, captured, roster, plan, surfaces] = await Promise.all([live.objects(), live.capturedObjects(), live.robots(), live.plan(), live.surfaces()]);
    const keys = LiveNames.objectKeys(catalog);
    const poses = captured[ObjectPosesKey.OBJECTS] ?? {};
    const objects = new Map([...keys].filter(([, key]) => poses[key]).map(([identifier, key]) => [identifier, poses[key]]));
    const robots = LiveNames.robots(roster, this.state.robots().map((robot) => robot[PlannedRobotKey.IDENTIFIER]));
    const nodes = LiveNames.stepNodes(plan);
    const statuses = this.state.steps().map((step, index) => nodes[index]?.[LivePlanNodeKey.STATUS] ?? null);
    const observations = this.state.steps().map((step, index) => new Map((nodes[index]?.[LivePlanNodeKey.CONSTRAINTS] ?? []).map((observed) => [observed[ConstraintObservationKey.TEXT], observed[ConstraintObservationKey.OBSERVATION] ?? null])));
    const byType = new Map();
    for (const surface of surfaces[SurfacesKey.SURFACES] ?? []) {
      byType.set(surface[SurfaceKey.TYPE], [...(byType.get(surface[SurfaceKey.TYPE]) ?? []), surface[SurfaceKey.NAME]]);
    }
    if (this.#run[RunStatusKey.MODE] === RunMode.PERFORM) await this.#sendConstraints(plan);
    return new PageWorld({ keys, objects, robots, statuses, observations, surfaces: byType, published: true });
  }

  /**
   * Attach the performing robot's constraints to its published plan, each once.
   * @param {Object} plan The live plan.
   * @returns {Promise<void>} Settles once every new constraint was sent.
   */
  async #sendConstraints(plan) {
    for (const request of LiveNames.constraintRequests(plan, this.state.steps())) {
      const key = JSON.stringify(request);
      if (this.#attached.has(key)) continue;
      this.#attached.add(key);
      await this.#live.attach(request).catch((error) => this.report(`The live plan refused a constraint: ${error.message}`));
    }
  }

  /**
   * Apply a marker dragged in the 3D view to the plan, and to the live world for an
   * object while it is published.
   * @param {Selection} selection The marker.
   * @param {Array<number>} pose Its new pose.
   */
  #placed(selection, pose) {
    if (selection.kind === MarkerKind.ROBOT) {
      const height = PlanPose.position(this.state.robot(selection.identifier)[PlannedRobotKey.POSE])[PoseIndex.Z];
      this.edit(() => this.state.setRobotPose(selection.identifier, PlanPose.of(...PlanPose.position(pose).slice(0, 2), height, PlanPose.yaw(pose))));
      return;
    }
    if (selection.kind === MarkerKind.TARGET) {
      this.edit(() => this.state.setTarget(selection.identifier, selection.field, pose));
      return;
    }
    this.placeObject(selection.identifier, pose);
  }

  /**
   * Move an object in the plan and, while its world is published, in the live world.
   * @param {string} identifier The object's identity.
   * @param {Array<number>} pose Where it starts.
   */
  placeObject(identifier, pose) {
    this.edit(() => this.state.setObjectPose(identifier, pose));
    const key = this.#world.keys.get(identifier);
    if (key) this.#live.move(key, pose, true).catch((error) => this.report(error.message));
  }

  // %% showing

  /**
   * @returns {Selection|null} The selected marker.
   */
  #selection() {
    return this.#parts.selection ?? null;
  }

  /**
   * Show the demo process's state and its newest output.
   */
  #showRun() {
    const state = this.#run[RunStatusKey.STATE];
    const running = state === RunState.RUNNING;
    const live = this.#world.published;
    this.#parts.runState.textContent = `${RUN_LABELS[state]}${running && live ? ' Its world is live.' : ''}`;
    this.#parts.runState.dataset.state = state;
    this.#parts.log.textContent = this.#run[RunStatusKey.LOG] ?? '';
    this.#parts.stop.disabled = !running;
    this.#parts.capture.disabled = !live;
    const runnable = this.state.catalog[PlanBuilderCatalogKey.MISSING].length === 0;
    for (const button of [this.#parts.stage, this.#parts.perform]) button.disabled = !runnable;
  }

  /**
   * Show the environment, the markers and the live poses in the 3D view.
   */
  #showScene() {
    if (!this.#scene) return;
    const environment = this.state.field(PlanKey.ENVIRONMENT) || null;
    if (environment !== this.#shownEnvironment) {
      this.#shownEnvironment = environment;
      this.#scene.showEnvironment(environment).then(() => this.#scene?.frame());
    }
    const robots = new Map([...this.#world.robots].map(([identifier, robot]) => [identifier, robot[RobotInstanceKey.POSE]]));
    this.#scene.show(this.state, { objects: this.#world.objects, robots });
  }

  // %% layout

  /**
   * Build the page's frame.
   * @param {HTMLElement} statusLine The line showing the page's state.
   */
  #layout(statusLine) {
    const elements = this.#elements;
    const parts = this.#parts;
    const document = this.#environment.document;
    parts.name = elements.input('text', PlanAction.NAME, () => this.edit(() => this.state.setField(PlanKey.NAME, parts.name.value.trim())));
    parts.task = elements.input('text', PlanAction.TASK, () => this.edit(() => this.state.setField(PlanKey.TASK, parts.task.value.trim())));
    parts.task.placeholder = 'What the plan does';
    parts.environment = new EnvironmentView(document, this);
    parts.saved = elements.select(PlanAction.OPEN, this.#planChoices(), OPEN_PROMPT.value, (value) => {
      if (value) this.#open(value).then(() => this.render());
    });
    const bar = elements.create('header', 'bar builder-bar');
    const plansRow = elements.create('div', 'button-row');
    plansRow.append(elements.button('New', PlanAction.NEW, () => this.#newPlan()), parts.saved, elements.button('Save', PlanAction.SAVE, () => this.#save()));
    bar.append(elements.create('strong', 'builder-title', 'Plan builder'), elements.label('name', parts.name), elements.label('task', parts.task), plansRow);

    parts.robots = new RobotsView(document, this);
    parts.steps = new StepsView(document, this);
    parts.objects = new ObjectsView(document, this);
    parts.constraints = new ConstraintsView(document, this, new ConstraintSentences(this.state.catalog[PlanBuilderCatalogKey.CONSTRAINT_RULES], this.#environment.storage));
    const side = elements.create('aside', 'builder-side');
    side.append(
      this.#section('Environment', parts.environment.element, 'Where the robots perform the plan.'),
      this.#section('Robots', parts.robots.element, 'Each robot performs a plan of its own; choose one to edit its plan, or click it in the 3D view.'),
      this.#section('Actions', parts.steps.palette, 'Drag an action into the plan, or click it.'),
      this.#section('Objects', parts.objects.element),
      this.#section('Constraints', parts.constraints.element, 'Drag a sentence onto a step.'),
    );
    parts.planTitle = elements.create('h2');
    const planColumn = elements.create('section', 'builder-plan');
    planColumn.append(parts.planTitle, parts.steps.list);

    parts.stage = elements.button('Start live scene', PlanAction.STAGE, () => this.#start(RunMode.STAGE));
    parts.perform = elements.button('Run plan', PlanAction.PERFORM, () => this.#start(RunMode.PERFORM));
    parts.stop = elements.button('Stop', PlanAction.STOP, () => this.#stop());
    parts.capture = elements.button('Capture live poses', PlanAction.CAPTURE, () => this.#capture());
    let turning = false;
    const turn = elements.button('Turn', PlanAction.TURN, () => {
      turning = !turning;
      turn.setAttribute('aria-pressed', String(turning));
      this.#scene?.setMode(turning ? TransformMode.TURN : TransformMode.MOVE);
    });
    turn.setAttribute('aria-pressed', 'false');
    const runRow = elements.create('div', 'button-row');
    runRow.append(
      parts.stage,
      parts.perform,
      parts.stop,
      parts.capture,
      turn,
      elements.button('Look at the plan', PlanAction.FRAME, () => this.#scene?.frameMarkers()),
      elements.button('Show demo', PlanAction.SHOW_DEMO, () => this.#showDemo()),
      elements.button('Write demo', PlanAction.WRITE_DEMO, () => this.#writeDemo()),
    );
    parts.runState = elements.create('span', 'run-state');
    parts.message = elements.create('span', 'message');
    parts.log = elements.create('pre', 'run-log');
    parts.output = elements.create('pre', 'demo-source');
    parts.output.hidden = true;
    const stage = elements.create('div', 'builder-stage');
    const controls = elements.create('div', 'builder-controls');
    const lines = elements.create('div', 'status-row');
    lines.append(parts.runState, parts.message);
    controls.append(runRow, lines, statusLine);
    const output = elements.create('div', 'builder-output');
    output.append(this.#details('Demo output', parts.log), this.#details('Generated demo', parts.output));
    const view = elements.create('section', 'builder-view');
    view.append(controls, stage, output);
    const main = elements.create('div', 'builder-main');
    main.append(side, planColumn, view);
    this.#root.replaceChildren(bar, main);
    if (this.#environment.createScene) {
      this.#scene = this.#environment.createScene(
        stage,
        new PlanSceneListeners(
          (selection) => {
            parts.selection = selection;
            parts.objects.render(selection?.kind === MarkerKind.OBJECT ? selection.identifier : null);
            const robot = selection?.kind === MarkerKind.ROBOT ? selection.identifier : null;
            if (robot && robot !== this.state.activeRobot()?.[PlannedRobotKey.IDENTIFIER]) this.edit(() => this.state.selectRobot(robot));
          },
          (selection, pose) => this.#placed(selection, pose),
          (error) => this.report(error.message),
        ),
      );
    } else {
      stage.append(elements.create('p', 'empty', 'This browser cannot show the 3D view; the plan can still be composed.'));
    }
  }

  /**
   * @returns {Array<{value: string, label: string}>} The choices of the saved plans'
   *   select.
   */
  #planChoices() {
    const plans = this.state.catalog[PlanBuilderCatalogKey.PLANS].map((summary) => ({ value: summary[PlanSummaryKey.IDENTIFIER], label: summary[PlanSummaryKey.NAME] }));
    return [OPEN_PROMPT, ...plans];
  }

  /**
   * @param {string} title The section's heading.
   * @param {HTMLElement} content Its content.
   * @param {string=} hint A line explaining it.
   * @returns {HTMLElement} The section.
   */
  #section(title, content, hint = '') {
    const section = this.#elements.create('section', 'builder-section');
    section.append(this.#elements.create('h2', '', title));
    if (hint) section.append(this.#elements.create('p', 'muted', hint));
    section.append(content);
    return section;
  }

  /**
   * @param {string} title The summary.
   * @param {HTMLElement} content What unfolds.
   * @returns {HTMLElement} The folded section.
   */
  #details(title, content) {
    const details = this.#elements.create('details');
    details.append(this.#elements.create('summary', '', title), content);
    return details;
  }

  /**
   * Stop polling and release every part, the 3D view and the listeners.
   */
  dispose() {
    if (this.#polling !== null) this.#environment.timer.cancel(this.#polling);
    this.#polling = null;
    for (const part of [this.#parts.environment, this.#parts.robots, this.#parts.steps, this.#parts.objects, this.#parts.constraints]) part?.dispose();
    this.#scene?.dispose();
    this.#scene = null;
    this.#elements.dispose();
  }
}

// %% live world

/**
 * What the live world showed at one poll, by the plan's identities.
 */
export class PageWorld {
  /**
   * @param {Object} parts `keys` (object keys by identity), `objects` (poses by
   *   identity), `robots` (live robots by identity), `statuses` (live step statuses by
   *   position), `observations` (each step's constraint observations by text, by
   *   position), `surfaces` (names by type) and `published` (whether a world is up).
   */
  constructor(parts) {
    /**
     * Each object's live key by its identity.
     * @type {Map<string, string>}
     */
    this.keys = parts.keys;
    /**
     * Each object's live pose by its identity.
     * @type {Map<string, Array<number>>}
     */
    this.objects = parts.objects;
    /**
     * Each robot's live instance by its identity.
     * @type {Map<string, Object>}
     */
    this.robots = parts.robots;
    /**
     * The live status of each of the performing robot's steps, by position.
     * @type {Array<string|null>}
     */
    this.statuses = parts.statuses;
    /**
     * What each of the performing robot's constraints observes, by its text, for each
     * step by position.
     * @type {Array<Map<string, string|null>>}
     */
    this.observations = parts.observations;
    /**
     * The live world's surface names by type.
     * @type {Map<string, Array<string>>}
     */
    this.surfaces = parts.surfaces;
    /**
     * Whether a world is published.
     * @type {boolean}
     */
    this.published = parts.published;
  }

  /**
   * @returns {PageWorld} The state without a live world.
   */
  static empty() {
    return new PageWorld({ keys: new Map(), objects: new Map(), robots: new Map(), statuses: [], observations: [], surfaces: new Map(), published: false });
  }

  /**
   * @returns {string} What decides whether the parts besides the 3D view change.
   */
  signature() {
    return JSON.stringify([this.statuses, this.observations.map((observed) => [...observed]), [...this.surfaces], [...this.keys]]);
  }
}
