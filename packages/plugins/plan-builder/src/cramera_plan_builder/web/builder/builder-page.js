/**
 * The builder page: lays out the plan's robots, actions, objects and constraints, the
 * steps, the 3D view and the demo controls, and connects them to the plan, the plan
 * builder's routes and the live publisher a started demo publishes on.
 *
 * Once a plan performs, the plan column shows the run view in place of the editable
 * steps until the person goes back to editing: each step's state, attempt, arm and
 * monitors, the perceived objects, the latest camera image and the run log, from the
 * events the run reports; the 3D view shows the live robot and objects as the run's world
 * holds them, read from the live publisher, the seam a real robot's joint states feed.
 * Without a run's world, the robot whose plan is edited stands in the posture the real
 * robot's drivers report, which the plan builder mirrors while attached to it.
 */

import {
  DemoSourceKey,
  DetectionGrounding,
  EnvironmentAnnotationsKey,
  IndexEntryKey,
  LoadedEnvironmentKey,
  UrdfFolderKey,
  ObjectPosesKey,
  LiveInfoKey,
  LivePlanKey,
  LivePlanNodeKey,
  PerceptionImageKey,
  PlanBuilderCatalogKey,
  PlanBuilderPageParameter,
  PlanKey,
  PlannedObjectKey,
  PlannedRobotKey,
  PlanRecordKey,
  PlanStepKey,
  PlanSummaryKey,
  RobotInstanceKey,
  RobotPostureKey,
  RobotProfileKey,
  PlanTemplateKey,
  ExecutorKind,
  RunMode,
  RunState,
  RunStatusKey,
  SavedDemoKey,
  SceneScanKey,
  StepConstraintKey,
  StepValidationKey,
  StepVerdict,
  ValidationReportKey,
  ConstraintObservationKey,
  ConstraintTextKey,
  SurfaceKey,
  SurfacesKey,
} from '../../../protocol.js';
import { PageStatus } from '../../../core/page-status.js';
import { RequestRefused } from './builder-api.js';
import { ConstraintSentences, ConstraintsView } from './constraints-view.js';
import { Elements, PlanAction } from './elements.js';
import { FreePlace } from './free-place.js';
import { LiveNames } from './live-client.js';
import { ObjectsView } from './objects-view.js';
import { MarkerKind, PlanSceneListeners, SceneOverlay, Selection, TransformMode } from './plan-scene.js';
import { PlanRefused, PlanState } from './plan-state.js';
import { PlanPose, PoseIndex } from './poses.js';
import { EnvironmentView, RobotsView } from './robots-view.js';
import { PollInterval } from '../../../live/live-session.js';
import { RunProgress, RunView } from './run-view.js';
import { SafetyBannerState, SafetyStopBanner } from './safety-stop.js';
import { REASON_TEXTS, StepsView } from './steps-view.js';

/**
 * How often a started demo and its live world are asked for their state, in
 * milliseconds.
 */
export const POLL_INTERVAL = 1000;

/**
 * How far, in metres, a live object may lie from its pose in the plan before the scene
 * counts as changed since the plan's validation.
 */
export const SCENE_TOLERANCE = 0.02;

/**
 * The storage key of the robot model the person used last, which a robot is added as.
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
 * The first option of the template choice, which starts no plan.
 */
const TEMPLATE_PROMPT = Object.freeze({ value: '', label: 'Start from a template…' });

/**
 * Where the browser keeps whether the palette offers every native action.
 */
export const DEVELOPER_MODE_KEY = 'cramera.plan-builder.developer-mode';

/**
 * How people read each state of the demo process.
 */
const RUN_LABELS = Object.freeze({
  [RunState.IDLE]: 'No demo runs.',
  [RunState.RUNNING]: 'The demo runs.',
  [RunState.SAVING]: 'The run is over and the robot holds; saving the run\'s record… Validate or run again once it is saved.',
  [RunState.FINISHED]: 'The demo finished.',
  [RunState.FAILED]: 'The demo failed; its output is below.',
  [RunState.STOPPED]: 'The demo was stopped.',
  [RunState.SAFETY_STOPPED]: 'A safety limit stopped the demo; the robot holds.',
  [RunState.SAVE_FAILED]: 'The run is over and the robot holds, but saving its record failed; its output is below.',
});

/**
 * What the page says once a demo of each run mode started.
 */
const RUN_MESSAGES = Object.freeze({
  [RunMode.STAGE]: 'Starting the live scene; building the world takes a while.',
  [RunMode.PERFORM]: 'Running the plan; watch it in the 3D view or the viewer.',
  [RunMode.SIMULATE]: 'Dry-running the plan in physics; watch it in the 3D view or the viewer.',
  [RunMode.ROBOT]: 'Running the plan on the robot; watch it in the 3D view or the viewer.',
});

/**
 * What the page says once a run on the real robot started.
 */
const REAL_ROBOT_RUN_MESSAGE = 'Running the plan on the real robot; keep the emergency stop at hand. The next run needs a new validation.';

/**
 * The run states in which the demo's process still runs and only Stop ends it.
 */
const ACTIVE_STATES = Object.freeze([RunState.RUNNING, RunState.SAVING]);

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

/**
 * @param {Object} report A `ValidationReport`.
 * @param {Array<Object>} steps The steps of the validated robot, in order.
 * @returns {string} What the page says about the validation: that it passed and how
 *   many steps are assumed, or the first step that fails and why.
 */
export function validationMessage(report, steps) {
  const validations = report[ValidationReportKey.STEPS];
  const seconds = `${report[ValidationReportKey.SECONDS].toFixed(1)} s`;
  const failed = validations.findIndex((step) => step[StepValidationKey.VERDICT] === StepVerdict.FAILED);
  if (failed >= 0) {
    const position = steps.findIndex((step) => step[PlanStepKey.IDENTIFIER] === validations[failed][StepValidationKey.STEP]);
    return `Validation failed at step ${position + 1}: ${REASON_TEXTS[validations[failed][StepValidationKey.REASON]] ?? 'it did not succeed'}. The plan cannot run on the robot (${seconds}).`;
  }
  const assumed = validations.filter((step) => step[StepValidationKey.VERDICT] === StepVerdict.ASSUMED).length;
  const note = assumed ? ` ${assumed === 1 ? '1 step is' : `${assumed} steps are`} assumed from the twin and checked again when the plan runs.` : '';
  return `The plan is valid and may run on the robot (${seconds}).${note}`;
}

/**
 * @param {Object} scan A `SceneScan`.
 * @returns {string} What the page says about the scan: how many objects the plan holds,
 *   whether they were seen or assumed from the twin, and how many found objects no
 *   model matches.
 */
export function scanMessage(scan) {
  const count = scan[SceneScanKey.OBJECTS].length;
  const objects = count === 1 ? '1 object' : `${count} objects`;
  const source = scan[SceneScanKey.GROUNDING] === DetectionGrounding.ASSUMED ? 'assumed from the twin, since the camera does not see the table; they are perceived again when the plan runs' : 'seen by the camera';
  const unrecognized = scan[SceneScanKey.UNRECOGNIZED];
  const left = unrecognized > 0 ? ` ${unrecognized} more found matched no object model and were left out.` : '';
  return `The scene holds ${objects}, ${source}.${left}`;
}

/**
 * @param {string} request What the person asked for, as the subject of a sentence.
 * @param {Error} error Why it failed.
 * @returns {string} What the page says about it: the plan builder's reason for a
 *   refusal, else that the request got no answer, as when the connection dropped.
 */
export function failureMessage(request, error) {
  if (error instanceof RequestRefused) return error.message;
  return `${request} got no answer from the plan builder (${error.message}); check that it still runs, then try again.`;
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
   * The shown environment's semantic annotation names by their class, as a plan run
   * finds them.
   * @type {Map<string, Array<string>>}
   */
  #environmentAnnotations = new Map();

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
   * The banner of the safety stop of the demo started last.
   */
  #safetyBanner = new SafetyStopBanner();

  /**
   * What the live world showed last: its object keys, poses and plan statuses.
   * @type {{keys: Map<string, string>, objects: Map<string, Array<number>>, robots: Map<string, Object>, statuses: Array<string|null>, surfaces: Map<string, Array<string>>, published: boolean}}
   */
  #world = PageWorld.empty();

  /**
   * Whether the plan column shows the run view rather than the editable steps.
   * @type {boolean}
   */
  #runShown = false;

  /**
   * The images of the latest perception step the live plan showed, each with the URL
   * it is served at; kept once the run ended.
   * @type {Array<Object>}
   */
  #cameraImages = [];

  /**
   * The constraint requests sent to the live plan, by node and text.
   * @type {Set<string>}
   */
  #attached = new Set();

  /**
   * The latest validation: the plan as it was validated, as JSON text, the
   * `ValidationReport` and whether the live scene changed since; null before one. A
   * plan or a scene that changed since is not validated.
   * @type {{plan: string, report: Object, sceneChanged: boolean}|null}
   */
  #validation = null;

  /**
   * What each robot model reaches, by the model's name: its `RobotReach` once the plan
   * builder answered, null while it is asked or when it could not be measured.
   * @type {Map<string, Object|null>}
   */
  #reaches = new Map();

  /**
   * The handle of the polling, or null.
   * @type {*}
   */
  #polling = null;

  /**
   * The handle of following the live robots and objects, or null.
   * @type {*}
   */
  #following = null;

  /**
   * Whether the live robots and objects are asked for right now, so asks do not pile
   * up.
   * @type {boolean}
   */
  #followed = false;

  /**
   * The joint positions the real robot's drivers reported last, by joint name; empty
   * while the builder is not attached to the real robot.
   * @type {Object<string, number>}
   */
  #mirrored = {};

  /**
   * Whether a poll is answered right now, so polls do not pile up.
   * @type {boolean}
   */
  #polled = false;

  /**
   * Whether a validation, a scan or the start of a run waits for its answer, during
   * which no other of them starts.
   * @type {boolean}
   */
  #waiting = false;

  /**
   * Whether a stop waits for the run to end, which takes a run on the real robot a
   * while as it halts the arms first.
   * @type {boolean}
   */
  #stopping = false;

  /**
   * Why the plan builder did not answer the latest poll, or null once it answered.
   * @type {string|null}
   */
  #unanswered = null;

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
    const profile = catalog[PlanBuilderCatalogKey.PROFILE];
    const configured = profile?.[RobotProfileKey.ENVIRONMENT] ?? null;
    const environment = environments.includes(asked) ? asked : (configured ?? environments[0] ?? null);
    this.#adopt(PlanState.empty(catalog, environment, profile?.[RobotProfileKey.ROBOT] ?? null));
    this.#layout(statusLine);
    const saved = query.get(PlanBuilderPageParameter.PLAN);
    if (saved) await this.#open(saved);
    this.render();
    const missing = catalog[PlanBuilderCatalogKey.MISSING];
    this.#pageStatus.ready(missing.length ? `The CRAM workspace is not importable here (missing ${missing.join(', ')}); plans can be composed and saved, not run.` : 'Compose the plan, then start the live scene or run it.');
    this.#polling = this.#environment.timer.repeat(() => this.#poll(), POLL_INTERVAL);
    this.#following = this.#environment.timer.repeat(() => this.#follow(), PollInterval.STATE);
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
    parts.steps.render(this.#world.statuses, this.#world.observations, this.#stepValidations());
    parts.objects.render(this.#selection()?.kind === MarkerKind.OBJECT ? this.#selection().identifier : null);
    parts.constraints.render();
    const robot = state.activeRobot();
    if (robot) this.#environment.storage.setItem(ROBOT_MODEL_KEY, robot[PlannedRobotKey.MODEL]);
    this.#showRun();
    this.#askReach();
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
   * @returns {string|null} The robot model the person used last, which a robot is
   *   added as unless they pick another.
   */
  preferredModel() {
    return this.#environment.storage.getItem(ROBOT_MODEL_KEY);
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
   * @returns {boolean} Whether no validation, scan or run may start now: one of them
   *   waits for its answer, or a plan runs, which only Stop may end, not another run.
   */
  busy() {
    return this.#waiting || this.#performing();
  }

  /**
   * @returns {boolean} Whether a plan runs or the record of its run is still saved; a
   *   staged live scene runs no plan, and a run started beside it replaces it.
   */
  #performing() {
    return ACTIVE_STATES.includes(this.#run[RunStatusKey.STATE]) && this.#run[RunStatusKey.MODE] !== RunMode.STAGE;
  }

  /**
   * Send a request no other validation, scan or run start may overlap, the buttons
   * starting them disabled until it answers.
   * @param {function(): Promise<*>} send Sends the request.
   * @returns {Promise<*>} Its answer.
   */
  #waitFor(send) {
    this.#waiting = true;
    this.render();
    return send().finally(() => {
      this.#waiting = false;
      this.render();
    });
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
   * @returns {Map<string, Array<string>>} The annotation names by their class: the shown
   *   environment's, and the live world's annotated surfaces while it runs.
   */
  surfaces() {
    const merged = new Map(this.#environmentAnnotations);
    for (const [type, names] of this.#world.surfaces) merged.set(type, [...new Set([...(merged.get(type) ?? []), ...names])]);
    return merged;
  }

  /**
   * Read the environment's semantic annotations and offer them to annotation fields.
   * @param {string|null} environment The environment bundle, or null for the floor.
   * @returns {Promise<void>} Settles once they are shown or refused.
   */
  async #readAnnotations(environment) {
    this.#environmentAnnotations = new Map();
    if (environment === null) return;
    const answer = await this.#environment.api.environmentAnnotations(environment).catch((error) => {
      this.report(error.message);
      return null;
    });
    if (!answer || environment !== this.#shownEnvironment) return;
    const byType = new Map();
    for (const annotation of answer[EnvironmentAnnotationsKey.ANNOTATIONS]) {
      byType.set(annotation[SurfaceKey.TYPE], [...(byType.get(annotation[SurfaceKey.TYPE]) ?? []), annotation[SurfaceKey.NAME]]);
    }
    this.#environmentAnnotations = byType;
    this.render();
  }

  // %% plans

  /**
   * Start a new plan in the shown environment.
   */
  #newPlan() {
    this.#planIdentifier = null;
    const profile = this.state.catalog[PlanBuilderCatalogKey.PROFILE];
    this.#adopt(PlanState.empty(this.state.catalog, this.state.field(PlanKey.ENVIRONMENT) || null, profile?.[RobotProfileKey.ROBOT] ?? null));
    this.report('New plan.');
    this.render();
  }

  /**
   * Start a new plan as a copy of one of the robot profile's templates.
   * @param {string} identifier The template's identity.
   */
  #newFromTemplate(identifier) {
    const template = this.state.catalog[PlanBuilderCatalogKey.TEMPLATES].find((entry) => entry[PlanTemplateKey.IDENTIFIER] === identifier);
    if (!template) return;
    this.#planIdentifier = null;
    this.#adopt(new PlanState(this.state.catalog, structuredClone(template[PlanTemplateKey.PLAN])));
    this.report(`New plan from the template ${template[PlanTemplateKey.PLAN][PlanKey.NAME]}.`);
    this.render();
  }

  /**
   * Show a plan, keeping the palette's mode.
   * @param {PlanState} state The plan to show.
   */
  #adopt(state) {
    state.setDeveloperMode(this.#environment.storage.getItem(DEVELOPER_MODE_KEY) === String(true));
    state.setMarkerSnap((pose) => this.freePlace().snapped(pose));
    this.state = state;
  }

  // %% free placing

  /**
   * @returns {FreePlace} Free placing for the edited robot: what its model reaches, once
   *   known, from where the plan stands it.
   */
  freePlace() {
    const robot = this.state.activeRobot();
    const reach = robot ? (this.#reaches.get(robot[PlannedRobotKey.MODEL]) ?? null) : null;
    return new FreePlace(reach, robot?.[PlannedRobotKey.POSE] ?? PlanPose.of(0, 0, 0, 0));
  }

  /**
   * Ask once what the edited robot's model reaches, and show the plan again once known.
   */
  #askReach() {
    const model = this.state.activeRobot()?.[PlannedRobotKey.MODEL];
    if (!model || this.#reaches.has(model) || !this.#environment.api.reach) return;
    this.#reaches.set(model, null);
    this.#environment.api.reach(model).then(
      (reach) => {
        this.#reaches.set(model, reach);
        this.render();
      },
      // without a measured reach, markers keep their height and colour
      () => {},
    );
  }

  /**
   * @param {Selection} selection A marker being dragged.
   * @param {Array<number>} pose Where it was dragged.
   * @returns {{pose: Array<number>, reachable: (boolean|null)}} Where it rests on the
   *   surface below it, and whether an arm of the edited robot may reach it there.
   */
  movingMarker(selection, pose) {
    const place = this.freePlace();
    const snapped = place.snapped(pose);
    return { pose: snapped, reachable: place.reaches(snapped) };
  }

  /**
   * @returns {SceneOverlay} The robot profile's zones on the edited robot's table, and
   *   whether an arm may reach each of its free-place markers.
   */
  #overlay() {
    const place = this.freePlace();
    const reachable = new Map();
    for (const step of this.state.steps()) {
      for (const target of this.state.targets(step)) {
        if (target.marker) reachable.set(new Selection(MarkerKind.TARGET, step[PlanStepKey.IDENTIFIER], target.field).key, place.reaches(target.pose));
      }
    }
    return new SceneOverlay(place.zones(this.state.zones()), reachable);
  }

  /**
   * Switch the palette between the robot profile's skills and every native action.
   * @param {boolean} enabled Whether the palette offers every native action.
   */
  #setDeveloperMode(enabled) {
    this.#environment.storage.setItem(DEVELOPER_MODE_KEY, String(enabled));
    this.state.setDeveloperMode(enabled);
    this.report(enabled ? 'Developer mode: every native action is offered.' : 'The robot profile\'s skills are offered.');
    this.render();
  }

  /**
   * @returns {Array<{value: string, label: string}>} The prompt and the robot profile's
   *   templates.
   */
  #templateChoices() {
    const templates = this.state.catalog[PlanBuilderCatalogKey.TEMPLATES] ?? [];
    return [TEMPLATE_PROMPT, ...templates.map((template) => ({ value: template[PlanTemplateKey.IDENTIFIER], label: template[PlanTemplateKey.PLAN][PlanKey.NAME] }))];
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
    this.#adopt(new PlanState(this.state.catalog, record[PlanRecordKey.DOCUMENT]));
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
   * @param {boolean} overrideValidation Whether a run needing a validated plan starts
   *   without one.
   * @returns {Promise<void>} Settles once the demo started or was refused.
   */
  async #start(mode, overrideValidation = false) {
    if (this.busy()) return;
    const status = await this.#waitFor(() => this.#environment.api.run(this.state.document, mode, overrideValidation)).catch((error) => {
      this.report(failureMessage('The run', error));
      return null;
    });
    if (!status) return;
    const real = mode === RunMode.ROBOT && this.#robotExecutor() === ExecutorKind.REAL;
    if (real) this.#validation = null;
    this.#safetyBanner.reset();
    this.#runShown = mode !== RunMode.STAGE;
    this.#cameraImages = [];
    this.#world = PageWorld.empty();
    this.#attached.clear();
    this.#run = status;
    this.report(real ? REAL_ROBOT_RUN_MESSAGE : RUN_MESSAGES[mode]);
    this.render();
  }

  /**
   * @returns {string|null|undefined} The `ExecutorKind` the robot profile runs the robot
   *   run mode with; null when the profile names executors but none for it, so the page
   *   offers no run on the robot; undefined when the server decides alone.
   */
  #robotExecutor() {
    const executors = this.state.catalog[PlanBuilderCatalogKey.PROFILE]?.[RobotProfileKey.EXECUTORS] ?? {};
    if (Object.keys(executors).length === 0) return undefined;
    return executors[RunMode.ROBOT] ?? null;
  }

  /**
   * Run the plan on the robot: once it passed its validation unchanged, or without one
   * in developer mode on a robot that is not the real one.
   * @returns {Promise<void>} Settles once the run started or was refused.
   */
  async #runOnRobot() {
    await this.#start(RunMode.ROBOT, !this.#validationPassed() && this.#mayOverrideValidation());
  }

  /**
   * @returns {boolean} Whether a run on the robot may start without a passed validation:
   *   in developer mode, and never on the real robot.
   */
  #mayOverrideValidation() {
    return this.state.developerMode() && this.#robotExecutor() !== ExecutorKind.REAL;
  }

  // %% validation

  /**
   * Validate the plan as it stands: every step of its robot is tried in a copy of the
   * twin, nothing moves.
   * @returns {Promise<void>} Settles once the report is shown or the validation refused.
   */
  async validate() {
    if (this.busy()) return;
    const plan = structuredClone(this.state.document);
    this.report('Validating the plan in a copy of the twin; nothing moves…');
    const report = await this.#waitFor(() => this.#environment.api.validate(plan)).catch((error) => {
      this.report(failureMessage('The validation', error));
      return null;
    });
    if (!report) return;
    this.#validation = { plan: JSON.stringify(plan), report, sceneChanged: false };
    this.render();
    this.report(validationMessage(report, this.state.steps()));
  }

  /**
   * @returns {Object|null} The `ValidationReport` of the plan as it stands, null when it
   *   or its scene changed since its latest validation or none ran.
   */
  validatedReport() {
    if (this.#validation === null || this.#validation.sceneChanged || this.#validation.plan !== JSON.stringify(this.state.document)) return null;
    return this.#validation.report;
  }

  /**
   * Invalidate the validation for good once a live object lies farther than
   * `SCENE_TOLERANCE` from its pose in the plan, which the validation took it at.
   */
  #noteSceneChange() {
    if (this.#validation === null || this.#validation.sceneChanged) return;
    const moved = this.state.objects().some((object) => {
      const live = this.#world.objects.get(object[PlannedObjectKey.IDENTIFIER]);
      if (live === undefined) return false;
      const planned = object[PlannedObjectKey.POSE];
      return Math.hypot(live[0] - planned[0], live[1] - planned[1], live[2] - planned[2]) > SCENE_TOLERANCE;
    });
    if (!moved) return;
    this.#validation.sceneChanged = true;
    this.render();
  }

  /**
   * @returns {boolean} Whether the plan as it stands passed its latest validation.
   */
  #validationPassed() {
    const report = this.validatedReport();
    return report !== null && report[ValidationReportKey.STEPS].every((step) => [StepVerdict.VALID, StepVerdict.ASSUMED].includes(step[StepValidationKey.VERDICT]));
  }

  /**
   * @returns {Map<string, Object>} How each step fared in the validation of the plan as
   *   it stands, by the step's identity; empty when it is not validated.
   */
  #stepValidations() {
    const report = this.validatedReport();
    return new Map((report?.[ValidationReportKey.STEPS] ?? []).map((step) => [step[StepValidationKey.STEP], step]));
  }

  /**
   * @returns {Promise<void>} Settles once the demo stopped or the stop failed, which is
   *   reported.
   */
  async #stop() {
    if (this.#stopping) return;
    this.#stopping = true;
    this.report('Stopping the run…');
    this.render();
    const status = await this.#environment.api.stop().catch((error) => {
      this.report(`The run could not be stopped: ${error.message}. Use the emergency stop if the robot still moves.`);
      return null;
    });
    this.#stopping = false;
    if (status) {
      this.#run = status;
      this.#world = PageWorld.empty();
      this.report('The run was stopped.');
    }
    this.render();
  }

  // %% safety stops

  /**
   * Acknowledge the safety stop of the demo, after which the plan restarts from its
   * beginning or is aborted.
   * @returns {Promise<void>} Settles once the plan builder acknowledged it.
   */
  async #acknowledgeStop() {
    const status = await this.#environment.api.acknowledge().catch((error) => {
      this.report(failureMessage('The acknowledgement', error));
      return null;
    });
    if (!status) return;
    this.#run = status;
    this.render();
  }

  /**
   * Run the plan again from its beginning, in the mode the stopped demo ran in.
   * @returns {Promise<void>} Settles once the run started or was refused.
   */
  async #restartPlan() {
    const mode = this.#run[RunStatusKey.MODE];
    this.#safetyBanner.settle();
    if (mode === RunMode.ROBOT) await this.#runOnRobot();
    else await this.#start(mode);
    this.render();
  }

  /**
   * Leave the plan stopped and the banner closed.
   */
  #abortPlan() {
    this.#safetyBanner.settle();
    this.report('The plan was aborted after its safety stop.');
    this.render();
  }

  /**
   * Show the banner of the demo's safety stop, if one is to be dealt with.
   */
  #showSafetyStop() {
    const state = this.#safetyBanner.state(this.#run);
    const parts = this.#parts;
    parts.safety.hidden = state === SafetyBannerState.HIDDEN;
    parts.safety.dataset.state = state;
    if (state === SafetyBannerState.HIDDEN) return;
    const revalidate = state === SafetyBannerState.ACKNOWLEDGED && this.#run[RunStatusKey.MODE] === RunMode.ROBOT && !this.#validationPassed() && !this.#mayOverrideValidation();
    parts.safetyMessage.textContent = `${this.#safetyBanner.message(this.#run)}${revalidate ? '. Validate the plan again before it restarts on the robot.' : ''}`;
    parts.restartPlan.disabled = revalidate || this.busy();
    parts.acknowledgeStop.hidden = state !== SafetyBannerState.VIOLATED;
    parts.restartPlan.hidden = state !== SafetyBannerState.ACKNOWLEDGED;
    parts.abortPlan.hidden = state !== SafetyBannerState.ACKNOWLEDGED;
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
    const run = await this.#environment.api.runStatus().then(
      (answer) => {
        this.#unanswered = null;
        return answer;
      },
      (error) => {
        this.#unanswered = error.message;
        return this.#run;
      },
    );
    const before = this.#run[RunStatusKey.STATE];
    this.#run = run;
    const world = LIVE_STATES.includes(run[RunStatusKey.STATE]) ? await this.#readWorld().catch(() => PageWorld.empty()) : PageWorld.empty();
    if (world.images.length > 0) this.#cameraImages = world.images;
    const changed = before !== run[RunStatusKey.STATE] || world.published !== this.#world.published || world.signature() !== this.#world.signature();
    this.#world = world;
    this.#polled = false;
    this.#noteSceneChange();
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
    const nodes = LiveNames.stepNodes(plan);
    const statuses = this.state.steps().map((step, index) => nodes[index]?.[LivePlanNodeKey.STATUS] ?? null);
    const observations = this.state.steps().map((step, index) => new Map((nodes[index]?.[LivePlanNodeKey.CONSTRAINTS] ?? []).map((observed) => [observed[ConstraintObservationKey.TEXT], observed[ConstraintObservationKey.OBSERVATION] ?? null])));
    const byType = new Map();
    for (const surface of surfaces[SurfacesKey.SURFACES] ?? []) {
      byType.set(surface[SurfaceKey.TYPE], [...(byType.get(surface[SurfaceKey.TYPE]) ?? []), surface[SurfaceKey.NAME]]);
    }
    if (this.#run[RunStatusKey.MODE] !== RunMode.STAGE) await this.#sendConstraints(plan);
    const seen = (plan[LivePlanKey.NODES] ?? []).filter((node) => (node[LivePlanNodeKey.IMAGES] ?? []).length > 0).at(-1);
    const images = (seen?.[LivePlanNodeKey.IMAGES] ?? []).map((image) => ({ ...image, url: live.perceptionImageUrl(image[PerceptionImageKey.FILE]) }));
    const world = new PageWorld({ keys, objects: new Map(), robots: new Map(), statuses, observations, surfaces: byType, images, published: true });
    world.move(roster, captured, this.#robotIdentities());
    return world;
  }

  /**
   * Move the robots and objects of a published live world in the 3D view as often as
   * the scene page does, between the polls of the run and its other parts.
   * @returns {Promise<void>} Settles once the live world answered.
   */
  async #follow() {
    if (this.#followed) return;
    if (!this.#world.published) return this.#followPosture();
    this.#followed = true;
    const live = this.#live;
    const answer = await Promise.all([live.robots(), live.capturedObjects()]).catch(() => null);
    this.#followed = false;
    if (!answer || !this.#world.published || !this.state) return;
    this.#world.move(...answer, this.#robotIdentities());
    this.#noteSceneChange();
    this.#showScene();
  }

  /**
   * Put the robot whose plan is edited in the posture the real robot reports, while no
   * run publishes a world.
   * @returns {Promise<void>} Settles once the plan builder answered.
   */
  async #followPosture() {
    this.#followed = true;
    const posture = await this.#environment.api.posture().catch(() => null);
    this.#followed = false;
    if (!posture || this.#world.published || !this.state) return;
    this.#mirrored = posture[RobotPostureKey.JOINT_POSITIONS] ?? {};
    if (Object.keys(this.#mirrored).length > 0) this.#showScene();
  }

  /**
   * @returns {Array<string>} The plan's robot identities, which namespace the live
   *   robots' names.
   */
  #robotIdentities() {
    return this.state.robots().map((robot) => robot[PlannedRobotKey.IDENTIFIER]);
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
   * Fill the plan's objects with what the robot finds on its table: where its camera
   * sees the table now through its perception, else as the twin holds them.
   * @returns {Promise<void>} Settles once the objects are filled or the scan refused.
   */
  async scanScene() {
    if (this.busy()) return;
    this.report('Scanning the scene…');
    const scan = await this.#waitFor(() => this.#environment.api.scan(this.state.document)).catch((error) => {
      this.report(failureMessage('The scan', error));
      return null;
    });
    if (!scan) return;
    this.edit(() => this.state.replaceObjects(scan[SceneScanKey.OBJECTS]));
    this.report(scanMessage(scan));
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
    const active = ACTIVE_STATES.includes(state);
    const live = this.#world.published;
    const unanswered = this.#unanswered === null ? '' : ` The plan builder does not answer (${this.#unanswered}); retrying.`;
    this.#parts.runState.textContent = `${RUN_LABELS[state]}${running && live ? ' Its world is live.' : ''}${unanswered}`;
    this.#parts.runState.dataset.state = state;
    this.#parts.log.textContent = this.#run[RunStatusKey.LOG] ?? '';
    this.#parts.stop.disabled = !active || this.#stopping;
    this.#parts.capture.disabled = !live;
    const runnable = this.state.catalog[PlanBuilderCatalogKey.MISSING].length === 0 && !this.#safetyBanner.blocksRuns(this.#run) && !this.busy();
    for (const button of [this.#parts.stage, this.#parts.perform, this.#parts.simulate, this.#parts.validate]) button.disabled = !runnable;
    const passed = this.#validationPassed();
    this.#parts.robot.disabled = !runnable || !(passed || this.#mayOverrideValidation());
    this.#showSafetyStop();
    this.#showRunView();
    this.#parts.validationState.textContent = this.#validationState(passed);
    this.#parts.validationState.dataset.passed = String(passed);
  }

  /**
   * Show the run view in the plan column while a run is to be followed, else the
   * editable steps.
   */
  #showRunView() {
    const parts = this.#parts;
    const robot = this.state.activeRobot();
    parts.steps.list.hidden = this.#runShown;
    parts.runView.element.hidden = !this.#runShown;
    parts.runToggle.textContent = this.#runShown ? 'Edit plan' : 'Show run';
    parts.runToggle.hidden = !this.#runShown && (this.#run[RunStatusKey.EVENTS] ?? []).length === 0;
    parts.planTitle.textContent = `${this.#runShown ? 'Run' : 'Plan'} of ${robot?.[PlannedRobotKey.LABEL] ?? 'no robot'}`;
    if (!this.#runShown) return;
    parts.runView.render(RunProgress.of(this.state.steps(), (step) => this.state.stepLabel(step), this.#run), this.#cameraImages);
  }

  /**
   * @param {boolean} passed Whether the plan as it stands passed its validation.
   * @returns {string} What the page says of the plan's validation beside the buttons.
   */
  #validationState(passed) {
    if (passed) return 'Validated: the plan may run on the robot.';
    if (this.validatedReport() !== null) return 'Validation failed: the plan cannot run on the robot.';
    const override = this.#mayOverrideValidation() ? ' Developer mode lets it run on the robot anyway.' : '';
    const changed = this.#validation === null ? 'Not validated' : this.#validation.sceneChanged ? 'The scene changed since its validation' : 'Changed since its validation';
    return `${changed}: validate the plan before it runs on the robot.${override}`;
  }

  /**
   * Show the environment, the markers and the live poses in the 3D view.
   */
  #showScene() {
    if (!this.#scene) return;
    const environment = this.state.field(PlanKey.ENVIRONMENT) || null;
    if (environment !== this.#shownEnvironment) {
      this.#shownEnvironment = environment;
      this.#readAnnotations(environment);
      this.#scene.showEnvironment(environment).then(() => this.#scene?.frame());
    }
    const robots = new Map([...this.#world.robots].map(([identifier, robot]) => [identifier, robot[RobotInstanceKey.POSE]]));
    const postures = new Map([...this.#world.robots].map(([identifier, robot]) => [identifier, robot[RobotInstanceKey.JOINT_POSITIONS] ?? {}]));
    const edited = this.state.activeRobot()?.[PlannedRobotKey.IDENTIFIER];
    if (!this.#world.published && edited !== undefined && Object.keys(this.#mirrored).length > 0) postures.set(edited, this.#mirrored);
    this.#scene.show(this.state, { objects: this.#world.objects, robots, postures, colors: this.#perceivedColors() }, this.#overlay());
  }

  /**
   * @returns {Map<string, string>} The color each object a run perceived shows, by the
   *   object's identity, which the 3D view tints it with.
   */
  #perceivedColors() {
    if (!this.#runShown) return new Map();
    const progress = RunProgress.of(this.state.steps(), (step) => this.state.stepLabel(step), this.#run);
    return new Map(progress.perceived.filter((seen) => seen.color).map((seen) => [seen.target, seen.color]));
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
    if ((this.state.catalog[PlanBuilderCatalogKey.TEMPLATES] ?? []).length > 0) {
      parts.templates = elements.select(PlanAction.NEW_FROM_TEMPLATE, this.#templateChoices(), TEMPLATE_PROMPT.value, (value) => {
        if (value) this.#newFromTemplate(value);
        parts.templates.value = TEMPLATE_PROMPT.value;
      });
      plansRow.append(parts.templates);
    }
    if (this.state.skills().length > 0) {
      parts.developer = elements.input('checkbox', PlanAction.DEVELOPER_MODE, () => this.#setDeveloperMode(parts.developer.checked));
      parts.developer.checked = this.state.developerMode();
      plansRow.append(elements.label('developer mode', parts.developer));
    }
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
    parts.runView = new RunView(elements);
    parts.runToggle = elements.button('Show run', PlanAction.TOGGLE_RUN, () => {
      this.#runShown = !this.#runShown;
      this.render();
    });
    const planHead = elements.create('div', 'plan-head');
    planHead.append(parts.planTitle, parts.runToggle);
    const planColumn = elements.create('section', 'builder-plan');
    planColumn.append(planHead, parts.steps.list, parts.runView.element);

    parts.stage = elements.button('Start live scene', PlanAction.STAGE, () => this.#start(RunMode.STAGE));
    parts.perform = elements.button('Run plan', PlanAction.PERFORM, () => this.#start(RunMode.PERFORM));
    parts.simulate = elements.button('Dry-run in physics', PlanAction.SIMULATE, () => this.#start(RunMode.SIMULATE));
    parts.validate = elements.button('Validate', PlanAction.VALIDATE, () => this.validate());
    const robotExecutor = this.#robotExecutor();
    const onRealRobot = robotExecutor === ExecutorKind.REAL;
    parts.robot = elements.button(onRealRobot ? 'Run on the real robot' : 'Run on robot', PlanAction.RUN_ON_ROBOT, () => this.#runOnRobot());
    parts.robot.hidden = robotExecutor === null;
    if (onRealRobot) {
      parts.robot.classList.add('real-robot');
      parts.robot.title = 'Moves the real robot. Runs a plan that passed its validation against where the robot stands now; keep the emergency stop at hand.';
    }
    parts.stop = elements.button('Stop', PlanAction.STOP, () => this.#stop());
    parts.capture = elements.button('Capture live poses', PlanAction.CAPTURE, () => this.#capture());
    parts.safetyMessage = elements.create('strong', 'safety-message');
    parts.acknowledgeStop = elements.button('Acknowledge', PlanAction.ACKNOWLEDGE_STOP, () => this.#acknowledgeStop());
    parts.restartPlan = elements.button('Restart from the beginning', PlanAction.RESTART_PLAN, () => this.#restartPlan());
    parts.abortPlan = elements.button('Abort', PlanAction.ABORT_PLAN, () => this.#abortPlan());
    parts.safety = elements.create('div', 'safety-banner');
    parts.safety.setAttribute('role', 'alert');
    parts.safety.hidden = true;
    parts.safety.append(parts.safetyMessage, parts.acknowledgeStop, parts.restartPlan, parts.abortPlan);
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
      parts.simulate,
      parts.validate,
      parts.robot,
      parts.stop,
      parts.capture,
      turn,
      elements.button('Look at the plan', PlanAction.FRAME, () => this.#scene?.frameMarkers()),
      elements.button('Show demo', PlanAction.SHOW_DEMO, () => this.#showDemo()),
      elements.button('Write demo', PlanAction.WRITE_DEMO, () => this.#writeDemo()),
    );
    parts.runState = elements.create('span', 'run-state');
    parts.validationState = elements.create('span', 'validation-state');
    parts.message = elements.create('span', 'message');
    parts.log = elements.create('pre', 'run-log');
    parts.output = elements.create('pre', 'demo-source');
    parts.output.hidden = true;
    const stage = elements.create('div', 'builder-stage');
    const controls = elements.create('div', 'builder-controls');
    const lines = elements.create('div', 'status-row');
    lines.append(parts.runState, parts.validationState, parts.message);
    controls.append(parts.safety, runRow, lines, statusLine);
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
          (selection, pose) => (selection.kind === MarkerKind.TARGET ? this.movingMarker(selection, pose) : null),
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
    for (const handle of [this.#polling, this.#following]) if (handle !== null) this.#environment.timer.cancel(handle);
    this.#polling = null;
    this.#following = null;
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
     * The images of the latest perception step of the live plan, each with the `url`
     * it is served at.
     * @type {Array<Object>}
     */
    this.images = parts.images ?? [];
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
    return new PageWorld({ keys: new Map(), objects: new Map(), robots: new Map(), statuses: [], observations: [], surfaces: new Map(), images: [], published: false });
  }

  /**
   * Take the live robots and the poses of the live objects this world has keys of.
   * @param {Object} roster The live robots.
   * @param {Object} captured Every free object's pose by key.
   * @param {Array<string>} identities The plan's robot identities.
   */
  move(roster, captured, identities) {
    const poses = captured[ObjectPosesKey.OBJECTS] ?? {};
    this.objects = new Map([...this.keys].filter(([, key]) => poses[key]).map(([identifier, key]) => [identifier, poses[key]]));
    this.robots = LiveNames.robots(roster, identities);
  }

  /**
   * @returns {string} What decides whether the parts besides the 3D view change.
   */
  signature() {
    return JSON.stringify([this.statuses, this.observations.map((observed) => [...observed]), [...this.surfaces], [...this.keys], this.images.map((image) => image.url)]);
  }
}
