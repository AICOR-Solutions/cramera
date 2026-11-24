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
  ArmReportKey,
  RobotPostureKey,
  RobotProfileKey,
  PerceptionSettingsKey,
  RuntimeCheck,
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
import { seenImageFigures } from './seen-images.js';
import { ConstraintSentences, ConstraintsView } from './constraints-view.js';
import { DomEvent, Elements, PlanAction, showText } from './elements.js';
import { FreePlace } from './free-place.js';
import { LiveNames } from './live-client.js';
import { ObjectsView } from './objects-view.js';
import { LEGEND, MarkerKind, PlanSceneListeners, SceneOverlay, Selection, TransformMode } from './plan-scene.js';
import { HistoryShortcut, HistoryTravel, PlanHistory, describeChange, editsText, historyShortcut } from './plan-history.js';
import { PlanRefused, PlanState } from './plan-state.js';
import { PlanPose, PoseIndex } from './poses.js';
import { EnvironmentView, REAL_ROBOT_POSE, RobotsView } from './robots-view.js';
import { PollInterval } from '../../../live/live-session.js';
import { RunProgress, RunView, withoutStopTraceback } from './run-view.js';
import { SafetyBannerState, SafetyStopBanner } from './safety-stop.js';
import { FlowFacts, FlowRequest, READY, Tone, cutOffOutcome, flowStatus, runOutcome } from './flow-status.js';
import { REASON_TEXTS, StepsView, stepParameters } from './steps-view.js';

/**
 * How often a started demo and its live world are asked for their state, in
 * milliseconds.
 */
export const POLL_INTERVAL = 1000;

/**
 * The longest wait, in milliseconds, between two polls of a plan builder that does not
 * answer: each poll it did not answer doubles the wait, from `POLL_INTERVAL` on, and
 * nothing else is asked of it meanwhile.
 */
export const UNANSWERED_POLL_LIMIT = 5000;

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
 * The storage key of the plan as the page showed it last, `{identifier, document}`:
 * the identity it was saved under, or null, and the plan. A page loaded again without a
 * plan named in its query shows it, so a reload or a second tab keeps the plan.
 */
export const DRAFT_KEY = 'cramera.plan-builder.draft';

/**
 * The choice of the saved plans' select that opens none.
 */
const OPEN_PROMPT = Object.freeze({ value: '', label: 'Open a saved plan…' });

/**
 * The first option of the template choice, which starts no plan.
 */
const TEMPLATE_PROMPT = Object.freeze({ value: '', label: 'Start from a template…' });

/**
 * The keys that move through a select's choices without opening it, which in some
 * browsers change its value at once, as typing a choice's first letter does; a choice
 * browsed to with them is taken only once the person presses Enter.
 */
const BROWSING_KEYS = Object.freeze(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown']);

/**
 * The key that takes the choice a select was browsed to.
 */
const CHOOSING_KEY = 'Enter';

/**
 * The keys the confirmation of a plan's replacement answers: Escape keeps editing, Tab
 * moves between its buttons and stays among them.
 */
const ConfirmKey = Object.freeze({ KEEP: 'Escape', NEXT: 'Tab' });

/**
 * What a select browsed by keyboard says of the choice it shows.
 */
const BROWSING_HINT = 'Press Enter to take this choice.';

/**
 * Where the browser keeps whether the palette offers every native action.
 */
export const DEVELOPER_MODE_KEY = 'cramera.plan-builder.developer-mode';

/**
 * The run states in which the demo's process still runs and only Stop ends it.
 */
const ACTIVE_STATES = Object.freeze([RunState.RUNNING, RunState.SAVING]);

/**
 * The run states in which the live world is published.
 */
const LIVE_STATES = Object.freeze([RunState.RUNNING]);

/**
 * How many characters a failure the status area shows may have; the output behind it
 * goes to the run output.
 */
export const FAILURE_LENGTH_LIMIT = 400;

/**
 * How many missing meshes a loaded environment's message names.
 */
export const NAMED_MISSING_MESHES = 3;

/**
 * The classes of the row holding the run on the robot alone, apart from the validation
 * and the simulated runs.
 */
export const ROBOT_RUN_ROW = 'button-row robot-actions';

/**
 * What stands before the run on the real robot in its row.
 */
const REAL_MOTION = 'Moves the real robot:';

/**
 * What the page says of the validation of a plan a run on the real robot took it away
 * from as it started, while the run goes on.
 */
export const VALIDATED_FOR_THIS_RUN = 'Validated for this run; validate again before the next run on the robot.';

/**
 * What the page says once a run on the real robot ended with the plan unchanged: the
 * run used its validation, so the next run needs a new one.
 */
export const VALIDATION_USED = 'The last run on the robot used this validation: validate again before the next run.';

/**
 * What the page says once a run left the plan's objects elsewhere than they started,
 * which the plan then takes: the live world does not tell which object a gripper
 * holds, so one still held keeps the pose it has in the gripper.
 */
export const OBJECTS_KEPT = 'The objects stay where the run left them; an object a robot still holds stays where its gripper has it.';

/**
 * What Undo and Redo name the changes the page makes itself rather than an edit of the
 * person's, which they cannot tell from the change alone.
 */
export const PageChange = Object.freeze({
  KEEP_OBJECTS: 'Keep the objects where the run left them',
  CAPTURE: 'Capture the live poses',
  SCAN: 'Fill the objects from the scan',
});

/**
 * What the page says once it cancelled a validation as the plan changed while it ran.
 */
export const VALIDATION_CANCELLED = 'Validation cancelled: the plan changed. Validate it again once it is ready.';

/**
 * What the page says once the plan builder no longer holds the validation the page
 * shows, which it keeps in memory only: after a restart, or once another plan was
 * validated since.
 */
export const VALIDATION_LOST = 'The plan builder restarted or validated another plan since, so this validation is gone: validate the plan again.';

/**
 * The HTTP status of a request the plan builder refuses as it conflicts with its state,
 * such as a run of a plan it holds no validation of.
 */
const CONFLICT_STATUS = 409;

/**
 * The label beside the run controls of a robot profile whose runs check leniently what
 * the camera perceives, and what it says when pointed at. A step goes ahead where the
 * plan expects its object: where the plan was validated, or, once the step was planned
 * again where the object was found, there.
 */
export const LENIENT_CHECK = Object.freeze({
  LABEL: 'Lenient camera check',
  TITLE: 'When the camera does not confirm an object, a step goes ahead where the plan expects it, and the run says so; safety limits, collision checks and Stop work as always.',
});

/**
 * The labels of the buttons starting a simulated run, by their `RunMode` value: what
 * each runs, in the person's words.
 */
export const RUN_LABELS = Object.freeze({
  [RunMode.STAGE]: 'Start live scene',
  [RunMode.PERFORM]: 'Simulate (no physics)',
  [RunMode.SIMULATE]: 'Simulate with physics',
});

/**
 * How each run mode executes the plan unless the robot profile names another executor,
 * as the plan builder's `DEFAULT_EXECUTORS` say.
 */
const DEFAULT_EXECUTORS = Object.freeze({ [RunMode.PERFORM]: ExecutorKind.KINEMATIC, [RunMode.SIMULATE]: ExecutorKind.PHYSICS });

/**
 * What a run button says when pointed at, by the `ExecutorKind` its run executes with:
 * what runs, and whether the robot moves.
 */
export const EXECUTOR_TITLES = Object.freeze({
  [ExecutorKind.KINEMATIC]: 'Runs the plan in simulation without physics: the simulated robot follows the planned motions and held objects move with the gripper, so it shows what the plan does, not whether a grasp holds. The real robot does not move.',
  [ExecutorKind.PHYSICS]: 'Runs the plan in simulation with physics (MuJoCo): objects are held by friction alone and can slip or fall, as on the real robot. The real robot does not move.',
  [ExecutorKind.PERCEIVED_PHYSICS]: 'Runs the plan in simulation with physics (MuJoCo), and the simulated camera looks for the plan\'s objects as the real robot\'s perception does. The real robot does not move.',
  [ExecutorKind.REAL]: 'Moves the real robot; keep the emergency stop at hand.',
});

/**
 * What the button starting the live scene says when pointed at, while the scene is
 * simulated.
 */
export const STAGE_TITLE = 'Shows the plan\'s world in a live simulation, where objects can be placed and their poses captured; no plan runs. The real robot does not move.';

/**
 * What the task field says: it describes the plan for people, and nothing reads it to
 * decide what the robot does.
 */
export const TASK_HINT = Object.freeze({
  PLACEHOLDER: 'A note for people, e.g. stack the cubes',
  TITLE: 'Describes the plan for the people who read it. The robot does not act on this text; only the steps decide what it does.',
});

/**
 * What each button of the 3D view's tools does, shown as its tooltip, by its
 * `PlanAction` value.
 */
export const TOOL_TITLES = Object.freeze({
  [PlanAction.CAPTURE]: 'Write where the live scene\'s robots and objects stand into the plan.',
  [PlanAction.TURN]: 'While on, the handle of the robot, object or target picked in the 3D view turns it around the vertical axis instead of moving it; click again to move.',
  [PlanAction.FRAME]: 'Point the 3D view at the plan\'s robots, objects and targets.',
  [PlanAction.SHOW_DEMO]: 'Show the Python script generated from the plan below the 3D view.',
  [PlanAction.WRITE_DEMO]: 'Write the script generated from the plan into the demos folder and say how to run it.',
});

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
 * @param {function(Object): string} label Names a step as its card does.
 * @returns {string} What the page says about the validation: that it passed and how
 *   many steps are assumed, or the first step that fails and why: what the validation
 *   found, as the step's card shows it, else the kind of failure.
 */
export function validationMessage(report, steps, label) {
  const validations = report[ValidationReportKey.STEPS];
  const seconds = `${report[ValidationReportKey.SECONDS].toFixed(1)} s`;
  const failed = validations.find((step) => step[StepValidationKey.VERDICT] === StepVerdict.FAILED);
  if (failed) {
    const position = steps.findIndex((step) => step[PlanStepKey.IDENTIFIER] === failed[StepValidationKey.STEP]);
    const detail = (failed[StepValidationKey.DETAIL] ?? '').split('\n').map((line) => line.trim()).filter(Boolean).join(' ');
    if (detail && position >= 0) return `Validation failed at step ${position + 1} (${label(steps[position])}): ${detail} (${seconds})`;
    return `Validation failed at step ${position + 1}: ${REASON_TEXTS[failed[StepValidationKey.REASON]] ?? 'it did not succeed'} (${seconds}).`;
  }
  const assumed = validations.filter((step) => step[StepValidationKey.VERDICT] === StepVerdict.ASSUMED).length;
  const note = assumed ? ` ${assumed === 1 ? '1 step' : `${assumed} steps`} assumed from the twin, checked again in the run.` : '';
  return `Validated in ${seconds}: ready to run on the robot.${note}`;
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
  const source = scan[SceneScanKey.GROUNDING] === DetectionGrounding.ASSUMED ? 'assumed from the twin since the camera does not see the table; perceived again in the run' : 'seen by the camera';
  const unrecognized = scan[SceneScanKey.UNRECOGNIZED];
  const left = unrecognized > 0 ? ` ${unrecognized} more matched no object model.` : '';
  return `Scanned: ${objects}, ${source}.${left}`;
}

/**
 * @param {string} request What the person asked for, as the subject of a sentence.
 * @param {Error} error Why it failed.
 * @returns {string} What the page says about it: the plan builder's reason for a
 *   refusal, else that the request got no answer, as when the connection dropped.
 */
export function failureMessage(request, error) {
  const message = error instanceof RequestRefused ? error.message : `${request} got no answer from the plan builder (${error.message}); check that it still runs, then try again.`;
  return message.length <= FAILURE_LENGTH_LIMIT ? message : `${message.slice(0, FAILURE_LENGTH_LIMIT - 1)}…`;
}

/**
 * What the 3D view shows, kept in its label's `data-mode`.
 */
export const ViewMode = Object.freeze({ PLAN: 'plan', SIMULATION: 'simulation', REAL: 'real' });

/**
 * @param {{published: boolean, mode: string|null, real: boolean, mirroring: boolean}} facts
 *   Whether a run publishes its world, the `RunMode` of the run, whether the robot run
 *   mode moves the real robot, and whether the robot stands in the posture the real
 *   robot's drivers report.
 * @returns {{mode: string, text: string}} What the 3D view shows, as a `ViewMode` and
 *   as its label says.
 */
export function viewMode(facts) {
  if (!facts.published) {
    const text = facts.mirroring ? 'Plan (not running); the robot stands as the real robot does' : 'Plan (not running)';
    return { mode: ViewMode.PLAN, text };
  }
  if (facts.mode === RunMode.ROBOT && facts.real) return { mode: ViewMode.REAL, text: 'Real robot (live)' };
  return { mode: ViewMode.SIMULATION, text: facts.mode === RunMode.STAGE ? 'Simulation (live scene)' : 'Simulation (live)' };
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
   *   with listeners, or null without WebGL), `timer` (`repeat(callback, interval)`
   *   answering a handle, `cancel(handle)`) and, optionally, `clock` (answers the time in
   *   milliseconds; `Date.now` by default) and `window` (the page's window, which asks
   *   before the page is left with unsaved changes; null by default).
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
    /**
     * Answers the time in milliseconds, which the status area counts waits with.
     * @type {function(): number}
     */
    this.clock = parts.clock ?? (() => Date.now());
    /**
     * The page's window, or null.
     * @type {EventTarget|null}
     */
    this.window = parts.window ?? null;
  }
}

// %% page

/**
 * @param {Array<Object>} arms The `ArmReport` of each arm of a mirrored posture.
 * @returns {string|null} Which arms' drivers went silent and for how long, or null
 *   while every arm reads as live.
 */
export function postureSilence(arms) {
  if (arms.length === 0) return 'No joint states from the robot yet';
  const silent = arms.filter((arm) => !arm[ArmReportKey.LIVE]).map((arm) => {
    const name = arm[ArmReportKey.ARM].replaceAll('_', ' ');
    const age = arm[ArmReportKey.AGE_SECONDS];
    const since = age === undefined || age === null ? 'yet' : `for ${Math.ceil(age)} s`;
    return `${name[0].toUpperCase()}${name.slice(1)}: no joint states ${since}`;
  });
  return silent.length === 0 ? null : silent.join('; ');
}

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
   * The plan as it was last saved, opened or started, as JSON text, which tells
   * whether it has unsaved changes; null when that is not known, as for a plan a reload
   * restored from an older page.
   * @type {string|null}
   */
  #baseline = null;

  /**
   * Replaces the plan once the person confirms losing its unsaved changes, or null while
   * nothing waits for that.
   * @type {function(): void|null}
   */
  #pendingReplace = null;

  /**
   * The plan's changes Undo and Redo travel, cleared for another plan.
   * @type {PlanHistory}
   */
  #history = new PlanHistory();

  /**
   * What had the keyboard focus before the confirmation of a replacement took it, given
   * back when the confirmation closes; null when nothing had it.
   * @type {HTMLElement|null}
   */
  #focusBeforeConfirm = null;

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
   * The validation waiting for its answer: the plan sent, as JSON text, and whether it
   * was cancelled as the plan changed since; null while none waits.
   * @type {{plan: string, cancelled: boolean}|null}
   */
  #validating = null;

  /**
   * The validation a run on the real robot took away as it started, which it gives
   * back when its check refused it before anything moved; null otherwise.
   * @type {{plan: string, report: Object, sceneChanged: boolean}|null}
   */
  #validationTaken = null;

  /**
   * The plan, as JSON text, whose validation the last run on the real robot used up as
   * it ended; null when no ended run used one.
   * @type {string|null}
   */
  #validationUsedBy = null;

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
   * Why the mirrored posture may not show where the real robot stands, or null while
   * it does or while the builder is not attached to the real robot.
   * @type {string|null}
   */
  #postureStale = null;

  /**
   * Whether the plan builder last said it mirrors the real robot's posture.
   * @type {boolean}
   */
  #mirroring = false;

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
   * The output of the process behind the latest failed request, shown as the run
   * output until the next request, or null.
   * @type {string|null}
   */
  #failureOutput = null;

  /**
   * Whether the plan is being saved, during which it is not changed, opened or saved.
   * @type {boolean}
   */
  #savingPlan = false;

  /**
   * Whether the progress of the run started last is hidden, since the plan changed
   * after it ended.
   * @type {boolean}
   */
  #progressHidden = false;

  /**
   * The plan the run started last ran, as JSON text, with its objects where the run
   * left them once it ended, or null when the page did not start it, as after a
   * reload; once the run ended, its progress counts only while the plan stays so.
   * @type {string|null}
   */
  #runPlan = null;

  /**
   * The poses the live world of the run of the plan last showed its objects at, by
   * identity, which the plan takes once the run ended; null while no run of the plan
   * published its world, as for a staged scene, which runs no plan.
   * @type {Map<string, Array<number>>|null}
   */
  #runObjects = null;

  /**
   * The validation, scan or run start waiting for its answer, or null.
   * @type {FlowRequest|null}
   */
  #request = null;

  /**
   * How the latest step ended, `{tone, text, validation}`, which the status area shows
   * until something new starts; null before one. `validation` marks the outcome of a
   * validation.
   * @type {{tone: string, text: string, validation?: boolean}|null}
   */
  #outcome = null;

  /**
   * What the status area counts the elapsed time of, and since when, in milliseconds.
   * @type {{phase: string|null, since: number}}
   */
  #phase = { phase: null, since: 0 };

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
   * Since when, by the environment's clock, the plan builder has not answered, or null
   * while it answers.
   * @type {number|null}
   */
  #unansweredSince = null;

  /**
   * When, by the environment's clock, a plan builder that does not answer is polled
   * next, and the wait after that poll, in milliseconds.
   * @type {{at: number, wait: number}}
   */
  #retry = { at: 0, wait: 0 };

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
    const draft = this.#environment.storage.getItem(DRAFT_KEY);
    if (saved) await this.#open(saved);
    else if (draft !== null) this.#restore(JSON.parse(draft));
    this.render();
    const missing = catalog[PlanBuilderCatalogKey.MISSING];
    this.#pageStatus.ready(missing.length ? `The CRAM workspace is not importable here (missing ${missing.join(', ')}); plans can be composed and saved, not run.` : READY);
    if (this.#environment.window) {
      this.#elements.listen(this.#environment.window, DomEvent.BEFORE_UNLOAD, (event) => this.#beforeLeaving(event));
      this.#elements.listen(this.#environment.window, DomEvent.KEY_DOWN, (event) => this.#historyKey(event));
    }
    this.#polling = this.#environment.timer.repeat(() => this.#poll(), POLL_INTERVAL);
    this.#following = this.#environment.timer.repeat(() => this.#follow(), PollInterval.STATE);
  }

  /**
   * Show the plan in every part.
   */
  render() {
    this.#cancelOutdatedValidation();
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
    this.#environment.storage.setItem(DRAFT_KEY, JSON.stringify({ identifier: this.#planIdentifier, document: state.document, saved: this.#baseline }));
    parts.replaceConfirm.hidden = this.#pendingReplace === null;
    this.#showRun();
    this.#askReach();
    this.#showScene();
  }

  // %% editing

  /**
   * Apply a change of the plan and show it; a change the plan refuses is reported. A
   * change of the plan is noted for Undo.
   * @param {function(): *} change The change.
   * @param {string|null} label What Undo names the change, or null to name it by what
   *   changed in the plan.
   */
  edit(change, label = null) {
    const before = JSON.stringify(this.state.document);
    // the boundary where an edit the plan refuses becomes a message for the person
    try {
      change();
    } catch (error) {
      if (!(error instanceof PlanRefused)) throw error;
      this.report(error.message, Tone.ERROR);
    }
    if (JSON.stringify(this.state.document) !== before) {
      this.#remember(before, label);
      // a changed plan is edited, no longer the one the run ended with
      if (!this.#performing()) this.#runShown = false;
    }
    this.render();
  }

  /**
   * Note a change of the plan for Undo.
   * @param {string} before The plan before the change, as JSON text.
   * @param {string|null} label What Undo names the change, or null to name it by what
   *   changed in the plan.
   */
  #remember(before, label) {
    this.#history.record(before, label ?? describeChange(JSON.parse(before), this.state.document, (step) => this.state.stepLabel(step)));
  }

  /**
   * Take back the latest change of the plan, unless a run locks the plan.
   */
  undo() {
    this.#travel(HistoryTravel.UNDO);
  }

  /**
   * Make the change taken back last again, unless a run locks the plan.
   */
  redo() {
    this.#travel(HistoryTravel.REDO);
  }

  /**
   * Show the plan on the other side of a change in the history. This changes the plan
   * like any edit: it counts as unsaved and as validated only while it is the plan the
   * latest validation validated, and objects moved back move in a published live world.
   * @param {string} travel A `HistoryTravel` value.
   */
  #travel(travel) {
    if (this.#historyLocked() !== null) return;
    const label = travel === HistoryTravel.UNDO ? this.#history.undoLabel() : this.#history.redoLabel();
    const current = JSON.stringify(this.state.document);
    const plan = travel === HistoryTravel.UNDO ? this.#history.undo(current) : this.#history.redo(current);
    if (plan === null) return;
    const before = this.state.document;
    this.state.restore(JSON.parse(plan));
    this.#moveLiveObjects(before);
    if (!this.#performing()) this.#runShown = false;
    this.report(`${travel === HistoryTravel.UNDO ? 'Undone' : 'Redone'}: ${label}.`);
    this.render();
  }

  /**
   * Move the objects the plan moved since it was as given in the live world, while it is
   * published, as a dragged object moves there.
   * @param {Object} before The plan document before.
   */
  #moveLiveObjects(before) {
    const poses = new Map(before[PlanKey.OBJECTS].map((object) => [object[PlannedObjectKey.IDENTIFIER], JSON.stringify(object[PlannedObjectKey.POSE])]));
    for (const object of this.state.objects()) {
      const identifier = object[PlannedObjectKey.IDENTIFIER];
      const key = this.#world.keys.get(identifier);
      if (!key || poses.get(identifier) === JSON.stringify(object[PlannedObjectKey.POSE])) continue;
      this.#live.move(key, object[PlannedObjectKey.POSE], true).catch((error) => this.report(error.message, Tone.ERROR));
    }
  }

  /**
   * @returns {string|null} Why Undo and Redo may not change the plan now, or null when
   *   they may: not while a run starts or goes, nor while the plan is saved.
   */
  #historyLocked() {
    return this.lockedByRun() ?? (this.#savingPlan ? 'Wait until the plan is saved.' : null);
  }

  /**
   * Undo or redo on Ctrl+Z, Ctrl+Shift+Z or Ctrl+Y (Cmd on macOS), except in a text
   * field, where the browser undoes the typing.
   * @param {KeyboardEvent} event The key pressed.
   */
  #historyKey(event) {
    const travel = historyShortcut(event);
    if (travel === null || editsText(event.target)) return;
    event.preventDefault();
    this.#travel(travel);
  }

  /**
   * Show whether Undo and Redo may be pressed, naming what they would change.
   */
  #showHistory() {
    const locked = this.#historyLocked();
    const buttons = [
      [this.#parts.undo, 'Undo', this.#history.undoLabel(), HistoryShortcut.UNDO],
      [this.#parts.redo, 'Redo', this.#history.redoLabel(), HistoryShortcut.REDO],
    ];
    for (const [button, verb, label, shortcut] of buttons) {
      button.disabled = locked !== null || label === null;
      button.title = locked ?? (label === null ? `Nothing to ${verb.toLowerCase()}.` : `${verb}: ${label} (${shortcut})`);
    }
  }

  /**
   * Write a URDF of the viewer's machine as an environment and start the plan there.
   * @param {string} path The URDF or xacro file.
   * @returns {Promise<void>} Settles once the environment is chosen or refused.
   */
  async loadEnvironment(path) {
    this.report(`Loading ${path}…`);
    const loaded = await this.#environment.api.loadEnvironment(path).catch((error) => {
      this.report(error.message, Tone.ERROR);
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
      this.report(error.message, Tone.ERROR);
      return null;
    });
    if (folder) storage.setItem(URDF_FOLDER_KEY, folder[UrdfFolderKey.PATH]);
    return folder;
  }

  /**
   * @param {Object} robot A robot of the plan.
   * @returns {boolean} Whether it is the real robot the builder is attached to: one of
   *   the robot profile's model while the profile's robot run mode moves the real
   *   robot, which a deployment attached to it alone offers.
   */
  realRobot(robot) {
    const profile = this.state.catalog[PlanBuilderCatalogKey.PROFILE];
    return this.#robotExecutor() === ExecutorKind.REAL && robot[PlannedRobotKey.MODEL] === profile?.[RobotProfileKey.ROBOT];
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
   * @param {FlowRequest} request What is asked, which the status area shows meanwhile.
   * @returns {Promise<*>} Its answer.
   */
  #waitFor(send, request) {
    this.#waiting = true;
    this.#request = request;
    this.#outcome = null;
    this.#failureOutput = null;
    this.report('');
    this.render();
    return send().finally(() => {
      this.#waiting = false;
      this.#request = null;
      this.render();
    });
  }

  /**
   * @param {string} message What the person should know.
   * @param {string} tone A `Tone` value: `Tone.ERROR` for a failure.
   */
  report(message, tone = Tone.IDLE) {
    this.#parts.message.textContent = message;
    this.#parts.message.dataset.tone = tone;
  }

  /**
   * Show how a step of the flow ended in the status area, where it stands until the
   * next step starts or a run ends.
   * @param {string} tone A `Tone` value.
   * @param {string} text What the person should know.
   * @param {boolean} validation Whether it tells how a validation ended, which stands
   *   only while the plan and its scene stay as validated.
   */
  #announce(tone, text, validation = false) {
    this.#outcome = { tone, text, validation };
    this.report('');
    this.render();
  }

  /**
   * Show why a request failed in the status area and the output of the process behind
   * it, if any, as the run output, opened.
   * @param {string} request What the person asked for, as the subject of a sentence.
   * @param {Error} error Why it failed.
   */
  #announceFailure(request, error) {
    this.#failureOutput = error.output ?? null;
    if (this.#failureOutput !== null) this.#parts.logDetails.open = true;
    this.#announce(Tone.ERROR, failureMessage(request, error));
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
      this.report(error.message, Tone.ERROR);
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
      this.report(error.message, Tone.ERROR);
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
      this.report(error.message, Tone.ERROR);
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
    this.#forgetRun();
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
    this.#forgetRun();
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
    this.#baseline = JSON.stringify(state.document);
    this.#pendingReplace = null;
    this.#history.clear();
    this.#validationUsedBy = null;
    // the validation was of the plan shown before, which this one never had
    this.#validation = null;
  }

  /**
   * @returns {boolean} Whether the plan changed since it was last saved, opened or
   *   started, or may have.
   */
  #unsaved() {
    return this.#baseline !== JSON.stringify(this.state.document);
  }

  /**
   * Have the browser ask before the page is left while the plan has unsaved changes.
   * @param {BeforeUnloadEvent} event The page about to be left.
   */
  #beforeLeaving(event) {
    if (!this.#unsaved()) return;
    event.preventDefault();
    // older browsers ask only for a return value
    event.returnValue = '';
  }

  /**
   * Replace the plan at once when it has no unsaved changes, else once the person
   * confirms losing them.
   * @param {string} replacement What replaces the plan, as the confirmation names it.
   * @param {function(): void} replace Replaces the plan.
   */
  #replacePlan(replacement, replace) {
    if (!this.#unsaved()) {
      replace();
      return;
    }
    this.#parts.replaceText.textContent = `“${this.state.field(PlanKey.NAME)}” has unsaved changes, which ${replacement} replaces. Save it first, or replace it and lose them?`;
    this.#pendingReplace = replace;
    this.#focusBeforeConfirm = this.#environment.document.activeElement ?? null;
    this.render();
    // the keyboard answers the question first, with the choice that loses nothing
    this.#parts.keepPlan.focus();
  }

  /**
   * Answer a key pressed in the confirmation: Escape keeps editing, Tab past its last
   * button comes back to its first and Shift+Tab the other way round.
   * @param {KeyboardEvent} event The key pressed.
   */
  #confirmKey(event) {
    const parts = this.#parts;
    if (event.key === ConfirmKey.KEEP) {
      event.preventDefault();
      this.#settleReplace(false);
      return;
    }
    if (event.key !== ConfirmKey.NEXT) return;
    const [first, last] = [parts.keepPlan, parts.replacePlan];
    const leaving = event.shiftKey ? event.target === first : event.target === last;
    if (!leaving) return;
    event.preventDefault();
    (event.shiftKey ? last : first).focus();
  }

  /**
   * Close the confirmation, replacing the plan when the person confirmed.
   * @param {boolean} confirmed Whether the person chose to lose the unsaved changes.
   */
  #settleReplace(confirmed) {
    const replace = this.#pendingReplace;
    const focused = this.#focusBeforeConfirm;
    this.#pendingReplace = null;
    this.#focusBeforeConfirm = null;
    if (confirmed && replace) replace();
    else this.render();
    focused?.focus();
  }

  /**
   * Hide how the run started last went, which concerns the plan shown before; a
   * safety stop still waiting for its acknowledgement stays.
   */
  #forgetRun() {
    this.#progressHidden = true;
    this.#runShown = false;
    this.#outcome = null;
    this.#failureOutput = null;
    this.#parts.runView?.clear();
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
    return new SceneOverlay(place.zones(this.state.zones()), reachable, this.#shownPerception());
  }

  /**
   * @returns {Object|null} The perception report the 3D view draws while a run is
   *   shown: the latest of the step that failed, else the latest of the run.
   */
  #shownPerception() {
    if (!this.#runShown) return null;
    const progress = this.#progress();
    const failed = progress.current();
    return failed?.perceptions.at(-1) ?? progress.perceptions.at(-1)?.report ?? null;
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
      this.report(error.message, Tone.ERROR);
      return null;
    });
    if (!record) return;
    this.#planIdentifier = record[PlanRecordKey.IDENTIFIER];
    this.#adopt(new PlanState(this.state.catalog, record[PlanRecordKey.DOCUMENT]));
  }

  /**
   * Show the plan the page showed last, under the identity it was saved under.
   * @param {{identifier: string|null, document: Object}} draft The plan as
   *   `DRAFT_KEY` keeps it.
   */
  #restore(draft) {
    this.#planIdentifier = draft.identifier;
    this.#adopt(new PlanState(this.state.catalog, draft.document));
    this.#baseline = draft.saved ?? null;
  }

  /**
   * Save the plan, under its identity once it has one.
   * @returns {Promise<void>} Settles once it is saved or refused.
   */
  async #save() {
    this.#savingPlan = true;
    this.render();
    const sent = JSON.stringify(this.state.document);
    const saved = await this.#environment.api.save(this.state.document, this.#planIdentifier).catch((error) => {
      this.report(error.message, Tone.ERROR);
      return null;
    }).finally(() => {
      this.#savingPlan = false;
      this.render();
    });
    if (!saved) return;
    this.#planIdentifier = saved[PlanRecordKey.IDENTIFIER];
    this.#baseline = sent;
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
    const demo = await this.#generateDemo();
    if (demo) this.report(`Generated ${demo[DemoSourceKey.FILE_NAME]}.`);
  }

  /**
   * Generate the demo from the plan and open it in the generated demo's section.
   * @returns {Promise<?Object>} The generated demo, or null once it was refused.
   */
  async #generateDemo() {
    const demo = await this.#environment.api.demo(this.state.document).catch((error) => {
      this.report(error.message, Tone.ERROR);
      return null;
    });
    if (!demo) return null;
    this.#parts.output.textContent = demo[DemoSourceKey.SOURCE];
    this.#parts.output.hidden = false;
    this.#parts.output.parentElement.open = true;
    return demo;
  }

  /**
   * Write the demo into the output directory and show what was written.
   * @returns {Promise<void>} Settles once it is written or refused.
   */
  async #writeDemo() {
    if (!(await this.#generateDemo())) return;
    const saved = await this.#environment.api.writeDemo(this.state.document).catch((error) => {
      this.report(error.message, Tone.ERROR);
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
    const status = await this.#waitFor(() => this.#environment.api.run(this.state.document, mode, overrideValidation), new FlowRequest(FlowRequest.START, mode)).catch(async (error) => {
      if (!(await this.#lostValidation(error))) this.#announceFailure('The run', error);
      return null;
    });
    if (!status) return;
    const real = mode === RunMode.ROBOT && this.#robotExecutor() === ExecutorKind.REAL;
    if (real) {
      this.#validationTaken = this.#validation;
      this.#validation = null;
    }
    this.#safetyBanner.reset();
    this.#runShown = mode !== RunMode.STAGE;
    this.#progressHidden = false;
    this.#runPlan = JSON.stringify(this.state.document);
    this.#runObjects = null;
    this.#cameraImages = [];
    this.#world = PageWorld.empty();
    this.#attached.clear();
    this.#run = status;
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
   *   in developer mode, and on the real robot only where the deployment allows it.
   */
  #mayOverrideValidation() {
    return this.state.developerMode() && (this.#robotExecutor() !== ExecutorKind.REAL || this.state.catalog[PlanBuilderCatalogKey.UNVALIDATED_REAL_RUNS] === true);
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
    const validating = { plan: JSON.stringify(plan), cancelled: false };
    this.#validating = validating;
    const send = () => this.#environment.api.validate(plan).finally(() => {
      this.#validating = null;
    });
    const report = await this.#waitFor(send, new FlowRequest(FlowRequest.VALIDATE)).catch((error) => {
      if (validating.cancelled) this.#announce(Tone.WARNING, VALIDATION_CANCELLED);
      else this.#announceFailure('The validation', error);
      return null;
    });
    if (!report) return;
    this.#validation = { plan: validating.plan, report, sceneChanged: false };
    if (validating.cancelled) this.#announce(Tone.WARNING, VALIDATION_CANCELLED);
    else this.#announce(this.#validationPassed() ? Tone.SUCCESS : Tone.ERROR, validationMessage(report, this.state.steps(), (step) => this.state.stepLabel(step)), true);
  }

  /**
   * Cancel the validation waiting for its answer once the plan differs from the one it
   * validates, so a new one may start as soon as it ended; a plan builder that cannot
   * cancel it is reported, and the validation's report then counts for its plan only.
   */
  #cancelOutdatedValidation() {
    const validating = this.#validating;
    if (validating === null || validating.cancelled || validating.plan === JSON.stringify(this.state.document)) return;
    validating.cancelled = true;
    if (this.#request !== null) this.#request.cancelled = true;
    this.#environment.api.cancelValidation().catch((error) => this.report(`The validation could not be cancelled: ${error.message}`, Tone.ERROR));
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
   * Drop the passed validation the page shows once the plan builder holds none, as it
   * restarted, and say so; the plan builder alone decides whether a plan may run.
   */
  #dropLostValidation() {
    if (!this.#validationPassed()) return;
    this.#validation = null;
    this.#announce(Tone.WARNING, VALIDATION_LOST);
  }

  /**
   * @param {Error} error Why the plan builder refused to start a run.
   * @returns {Promise<boolean>} Whether the refusal came as the plan builder holds no
   *   validation of the plan the page shows as validated, which the page then drops.
   */
  async #lostValidation(error) {
    if (error.status !== CONFLICT_STATUS || !this.#validationPassed()) return false;
    const run = await this.#environment.api.runStatus().catch(() => null);
    if (run?.[RunStatusKey.VALIDATION_HELD] !== false) return false;
    this.#dropLostValidation();
    return true;
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
    this.render();
    const status = await this.#environment.api.stop().catch((error) => {
      this.#outcome = { tone: Tone.ERROR, text: `The run could not be stopped: ${error.message}. Use the emergency stop if the robot still moves.` };
      return null;
    });
    this.#stopping = false;
    if (status) {
      this.#run = status;
      this.#world = PageWorld.empty();
      this.#keepRunObjects();
      this.#outcome = runOutcome(status, this.#progress(), this.#robotExecutor() === ExecutorKind.REAL) ?? { tone: Tone.WARNING, text: 'The run was stopped.' };
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
      this.#announce(Tone.ERROR, failureMessage('The acknowledgement', error));
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
    this.#announce(Tone.WARNING, 'The plan was aborted after its safety stop.');
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
    const revalidate = this.#revalidate();
    showText(parts.safetyMessage, `${this.#safetyBanner.message(this.#run)}${revalidate ? '. Validate the plan again before restarting it on the robot.' : ''}`);
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
    }, PageChange.CAPTURE);
  }

  // %% live world

  /**
   * Ask the demo process and, while it runs, its live world for their state.
   * @returns {Promise<void>} Settles once both answered.
   */
  async #poll() {
    if (this.#polled || !this.state) return;
    if (this.#unanswered !== null && this.#environment.clock() < this.#retry.at) {
      this.#showFlowStatus();
      return;
    }
    this.#polled = true;
    const validation = this.#validation;
    let answered = false;
    const run = await this.#environment.api.runStatus().then(
      (answer) => {
        answered = true;
        this.#unanswered = null;
        this.#unansweredSince = null;
        this.#retry = { at: 0, wait: 0 };
        return answer;
      },
      (error) => {
        const now = this.#environment.clock();
        this.#unanswered = error.message;
        this.#unansweredSince ??= now;
        const wait = Math.min(Math.max(2 * this.#retry.wait, POLL_INTERVAL), UNANSWERED_POLL_LIMIT);
        this.#retry = { at: now + wait, wait };
        return this.#run;
      },
    );
    const previous = this.#run;
    const before = previous[RunStatusKey.STATE];
    this.#run = run;
    if (this.#performing()) this.#progressHidden = false;
    if (before !== run[RunStatusKey.STATE]) this.#noteRunEnd(previous);
    if (!LIVE_STATES.includes(run[RunStatusKey.STATE])) this.#keepRunObjects();
    // a validation answered while the status was asked for is newer than the status
    if (answered && this.#validation === validation && run[RunStatusKey.VALIDATION_HELD] === false) this.#dropLostValidation();
    const world = this.#publishes(run) ? await this.#readWorld().catch(() => PageWorld.empty()) : PageWorld.empty();
    if (world.images.length > 0) this.#cameraImages = world.images;
    const changed = before !== run[RunStatusKey.STATE] || world.published !== this.#world.published || world.signature() !== this.#world.signature();
    this.#world = world;
    this.#polled = false;
    this.#noteRunObjects();
    this.#noteSceneChange();
    if (changed) this.render();
    else {
      this.#showRun();
      this.#showScene();
    }
  }

  /**
   * Note the object poses a published live world of a run of the plan shows as the
   * last ones the run left its objects at.
   */
  #noteRunObjects() {
    if (this.#world.published && this.#run[RunStatusKey.MODE] !== RunMode.STAGE) this.#runObjects = this.#world.objects;
  }

  /**
   * Once a run of the plan ended, put the plan's objects where its live world last
   * showed them and say so; an object it showed no pose of keeps its pose. This is a
   * change of the plan like any other, unsaved and no longer validated, but the run
   * still counts against it and its validation stays used by the run.
   */
  #keepRunObjects() {
    const left = this.#runObjects;
    this.#runObjects = null;
    if (left === null) return;
    const ran = JSON.stringify(this.state.document);
    for (const object of this.state.objects()) {
      const identifier = object[PlannedObjectKey.IDENTIFIER];
      const pose = left.get(identifier)?.map(PlanPose.rounded);
      if (pose !== undefined && JSON.stringify(pose) !== JSON.stringify(object[PlannedObjectKey.POSE])) this.state.setObjectPose(identifier, pose);
    }
    const kept = JSON.stringify(this.state.document);
    if (kept === ran) return;
    this.#remember(ran, PageChange.KEEP_OBJECTS);
    // the poses are what the run did, not an edit of the person after it
    if (this.#runPlan === ran) this.#runPlan = kept;
    if (this.#validationUsedBy === ran) this.#validationUsedBy = kept;
    this.report(OBJECTS_KEPT);
    this.render();
  }

  /**
   * @param {Object} run A `RunStatus`.
   * @returns {boolean} Whether the run's live world may be published, so its publisher
   *   is asked for it: once it runs, and for a run on the real robot once it reported
   *   its steps, which it does only after its publisher started. Asked earlier, the
   *   publisher's closed port fails every poll for the half minute a real run prepares.
   */
  #publishes(run) {
    if (!LIVE_STATES.includes(run[RunStatusKey.STATE])) return false;
    const real = run[RunStatusKey.MODE] === RunMode.ROBOT && this.#robotExecutor() === ExecutorKind.REAL;
    return !real || (run[RunStatusKey.EVENTS] ?? []).length > 0;
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
    if (this.#followed || this.#unanswered !== null) return;
    if (!this.#world.published) return this.#followPosture();
    this.#followed = true;
    const live = this.#live;
    const answer = await Promise.all([live.robots(), live.capturedObjects()]).catch(() => null);
    this.#followed = false;
    if (!answer || !this.#world.published || !this.state) return;
    this.#world.move(...answer, this.#robotIdentities());
    this.#noteRunObjects();
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
    const answer = await this.#environment.api.posture().catch((error) => error);
    this.#followed = false;
    if (this.#world.published || !this.state) return;
    if (answer instanceof Error) {
      if (!this.#mirroring) return;
      this.#postureStale = `The plan builder does not answer (${answer.message})`;
      this.#showScene();
      return;
    }
    this.#mirrored = answer[RobotPostureKey.JOINT_POSITIONS] ?? {};
    this.#mirroring = answer[RobotPostureKey.MIRRORED] ?? false;
    this.#postureStale = this.#mirroring ? postureSilence(answer[RobotPostureKey.ARMS] ?? []) : null;
    if (this.#mirroring || Object.keys(this.#mirrored).length > 0) this.#showScene();
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
      await this.#live.attach(request).catch((error) => this.report(`The live plan refused a constraint: ${error.message}`, Tone.ERROR));
    }
  }

  /**
   * Apply a marker dragged in the 3D view to the plan, and to the live world for an
   * object while it is published; a robot's marker goes back while a run goes, which
   * says so.
   * @param {Selection} selection The marker.
   * @param {Array<number>} pose Its new pose.
   */
  #placed(selection, pose) {
    if (selection.kind === MarkerKind.ROBOT) {
      const locked = this.realRobot(this.state.robot(selection.identifier)) ? REAL_ROBOT_POSE.NOTE : this.lockedByRun();
      if (locked !== null) {
        this.report(locked);
        this.render();
        return;
      }
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
    const scan = await this.#waitFor(() => this.#environment.api.scan(this.state.document), new FlowRequest(FlowRequest.SCAN)).catch((error) => {
      this.#announceFailure('The scan', error);
      return null;
    });
    if (!scan) return;
    // Where a scan finds the objects is the robot's view of the table, not the person's
    // edit, and a new scan finds it again: a plan without unsaved changes keeps none. A
    // plan with some keeps them, so no edit of the person's is ever replaced unasked.
    const unchanged = !this.#unsaved();
    this.edit(() => {
      this.state.replaceObjects(scan[SceneScanKey.OBJECTS]);
      if (unchanged) this.#baseline = JSON.stringify(this.state.document);
    }, PageChange.SCAN);
    // what perception saw, opened; hidden after a scan that drew nothing
    const images = scan[SceneScanKey.IMAGES] ?? [];
    this.#parts.scanFigures.replaceChildren(...seenImageFigures(this.#elements, images));
    this.#parts.scanImages.hidden = images.length === 0;
    this.#parts.scanImages.open = images.length > 0;
    this.#announce(Tone.SUCCESS, scanMessage(scan));
  }

  /**
   * Move an object in the plan and, while its world is published, in the live world.
   * @param {string} identifier The object's identity.
   * @param {Array<number>} pose Where it starts.
   */
  placeObject(identifier, pose) {
    this.edit(() => this.state.setObjectPose(identifier, pose));
    const key = this.#world.keys.get(identifier);
    if (key) this.#live.move(key, pose, true).catch((error) => this.report(error.message, Tone.ERROR));
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
    const active = ACTIVE_STATES.includes(state);
    const parts = this.#parts;
    parts.runState.dataset.state = state;
    const log = this.#run[RunStatusKey.LOG] ?? '';
    showText(parts.log, this.#failureOutput ?? (this.#progressHidden ? '' : state === RunState.STOPPED ? withoutStopTraceback(log) : log));
    parts.stop.disabled = !active || this.#stopping;
    parts.capture.disabled = !this.#world.published;
    const blocked = this.#blocked();
    for (const button of [parts.stage, parts.perform, parts.simulate, parts.validate, parts.scan]) button.disabled = blocked !== null;
    const passed = this.#validationPassed();
    parts.robot.disabled = blocked !== null || !(passed || this.#mayOverrideValidation());
    this.#showSafetyStop();
    this.#showRunView();
    showText(parts.validationState, this.#validationState(passed));
    parts.validationState.dataset.passed = String(passed);
    this.#showFlowStatus();
    this.#showButtons(blocked, passed, active);
  }

  /**
   * @returns {string|null} Why no validation, scan or run may start now, or null when
   *   they may.
   */
  #blocked() {
    if (this.state.catalog[PlanBuilderCatalogKey.MISSING].length > 0) return 'The CRAM workspace is not importable here.';
    if (this.#safetyBanner.blocksRuns(this.#run)) return 'Acknowledge the safety stop first.';
    if (this.#waiting) return 'Wait until the current request is answered.';
    if (this.#performing()) return 'Only Stop is offered while the plan runs.';
    return null;
  }

  /**
   * @returns {RunProgress} Where the run started last stands, by the edited robot's steps.
   */
  #progress() {
    const run = this.#runCounted() ? this.#run : { ...this.#run, [RunStatusKey.EVENTS]: [] };
    return RunProgress.of(this.state.steps(), (step) => this.state.stepLabel(step), run, (step) => stepParameters(this.state, step));
  }

  /**
   * @returns {boolean} Whether the events of the run started last count against the
   *   plan as it stands: not once the plan was replaced, nor once a run that ended was
   *   followed by a change of its plan, whose steps it would otherwise count anew.
   */
  #runCounted() {
    if (this.#progressHidden) return false;
    return this.#performing() || this.#runPlan === null || this.#runPlan === JSON.stringify(this.state.document);
  }

  /**
   * Keep how the run started last ended as the outcome the status area shows, and open
   * its output when it failed; a run the plan builder no longer knows, as it restarted,
   * was cut off.
   * @param {Object} previous The `RunStatus` the plan builder reported before.
   */
  #noteRunEnd(previous) {
    if (this.#run[RunStatusKey.STATE] === RunState.REFUSED && this.#validation === null) this.#validation = this.#validationTaken;
    // a run saving its record still runs with the validation it took
    if (!ACTIVE_STATES.includes(this.#run[RunStatusKey.STATE])) {
      if (this.#validationTaken !== null && this.#validation === null) this.#validationUsedBy = this.#validationTaken.plan;
      this.#validationTaken = null;
    }
    const real = this.#robotExecutor() === ExecutorKind.REAL;
    const outcome = cutOffOutcome(previous, this.#run, real) ?? runOutcome(this.#run, this.#progress(), real);
    if (outcome === null) return;
    this.#outcome = outcome;
    if (outcome.tone === Tone.ERROR) this.#parts.logDetails.open = true;
  }

  /**
   * @returns {{tone: string, text: string}|null} The outcome the status area shows: the
   *   latest step's, except that the outcome of a validation whose plan or scene changed
   *   since says the plan needs validating again.
   */
  #standingOutcome() {
    if (!this.#outcome?.validation || this.#validation === null || this.validatedReport() !== null) return this.#outcome;
    return { tone: Tone.WARNING, text: this.#validationState(false) };
  }

  /**
   * Show where the flow stands in the status area: what happens, in the colour of its
   * kind, with a spinner and the seconds waited while the page waits.
   */
  #showFlowStatus() {
    const facts = new FlowFacts({
      run: this.#run,
      progress: this.#progress(),
      real: this.#robotExecutor() === ExecutorKind.REAL,
      live: this.#world.published,
      request: this.#request,
      stopping: this.#stopping,
      unanswered: this.#unanswered,
      unansweredFor: this.#unansweredSince === null ? 0 : this.#environment.clock() - this.#unansweredSince,
      safety: this.#safetyBanner.state(this.#run),
      revalidate: this.#revalidate(),
      outcome: this.#standingOutcome(),
      missing: this.state.catalog[PlanBuilderCatalogKey.MISSING],
    });
    const status = flowStatus(facts);
    const now = this.#environment.clock();
    if (status.phase !== this.#phase.phase) this.#phase = { phase: status.phase, since: now };
    const parts = this.#parts;
    parts.flow.dataset.tone = status.tone;
    parts.flow.dataset.busy = String(status.phase !== null);
    parts.flow.setAttribute('aria-live', status.tone === Tone.ERROR ? 'assertive' : 'polite');
    showText(parts.runState, status.text);
    showText(parts.elapsed, status.phase === null ? '' : `${Math.floor((now - this.#phase.since) / 1000)} s`);
  }

  /**
   * Mark the button whose request the page waits for, the next step of the flow and the
   * reason each start button is disabled.
   * @param {string|null} blocked Why no validation, scan or run may start now.
   * @param {boolean} passed Whether the plan as it stands passed its validation.
   * @param {boolean} active Whether the demo's process runs.
   */
  #showButtons(blocked, passed, active) {
    const parts = this.#parts;
    const request = this.#request;
    const modes = { [RunMode.STAGE]: parts.stage, [RunMode.PERFORM]: parts.perform, [RunMode.SIMULATE]: parts.simulate, [RunMode.ROBOT]: parts.robot };
    const waited = request === null ? null : request.kind === FlowRequest.SCAN ? parts.scan : request.kind === FlowRequest.VALIDATE ? parts.validate : modes[request.mode];
    for (const button of [parts.scan, parts.validate, parts.stage, parts.perform, parts.simulate, parts.robot, parts.stop]) {
      const busy = button === waited || (button === parts.stop && this.#stopping);
      button.dataset.busy = String(busy);
      button.setAttribute('aria-busy', String(busy));
    }
    parts.validate.classList.toggle('primary', blocked === null && !passed);
    for (const button of [parts.scan, parts.validate, parts.stage, parts.perform, parts.simulate]) button.title = button.disabled ? blocked ?? '' : (button.dataset.hint ?? '');
    parts.robot.title = parts.robot.disabled ? blocked ?? this.#validationState(passed) : (parts.robot.dataset.hint ?? '');
    const locked = this.#planLocked();
    for (const control of [parts.newPlan, parts.saved, parts.save, parts.templates, parts.replacePlan].filter(Boolean)) {
      control.disabled = locked !== null;
      control.title = locked ?? '';
    }
    parts.stop.title = parts.stop.disabled ? (this.#stopping ? 'Stopping the run…' : 'No run to stop.') : 'Stop the run; the robot halts.';
    this.#showHistory();
  }

  /**
   * @returns {string|null} Why the robots and the plan may not be changed while a run
   *   starts or goes, or null when no run does.
   */
  lockedByRun() {
    return this.#performing() || this.#request?.kind === FlowRequest.START ? 'Wait until the run ends.' : null;
  }

  /**
   * @returns {string|null} Why the plan may not be changed, opened or saved now, or null
   *   when it may.
   */
  #planLocked() {
    const run = this.lockedByRun();
    if (run !== null) return run;
    if (this.#request !== null) return 'Wait until the current request is answered.';
    if (this.#savingPlan) return 'Wait until the plan is saved.';
    return null;
  }

  /**
   * @returns {boolean} Whether an acknowledged safety stop of a run on the robot needs a
   *   new validation before the plan restarts.
   */
  #revalidate() {
    return this.#safetyBanner.state(this.#run) === SafetyBannerState.ACKNOWLEDGED && this.#run[RunStatusKey.MODE] === RunMode.ROBOT && !this.#validationPassed() && !this.#mayOverrideValidation();
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
    showText(parts.runToggle, this.#runShown ? 'Edit plan' : 'Show run');
    parts.runToggle.hidden = !this.#runShown && (!this.#runCounted() || (this.#run[RunStatusKey.EVENTS] ?? []).length === 0);
    showText(parts.planTitle, `${this.#runShown ? 'Run' : 'Plan'} of ${robot?.[PlannedRobotKey.LABEL] ?? 'no robot'}`);
    if (!this.#runShown) return;
    parts.runView.render(this.#progress(), this.#cameraImages);
  }

  /**
   * @param {boolean} passed Whether the plan as it stands passed its validation.
   * @returns {string} What the page says of the plan's validation beside the buttons.
   */
  #validationState(passed) {
    if (passed) return 'Validated.';
    // a run on the real robot takes the validation away as it starts, for the next run
    if (this.#performing() && this.#validationTaken !== null) return VALIDATED_FOR_THIS_RUN;
    if (this.validatedReport() !== null) return 'Validation failed: the plan cannot run on the robot.';
    const where = this.#robotExecutor() === ExecutorKind.REAL ? 'real robot anyway, unchecked' : 'robot anyway';
    const override = this.#mayOverrideValidation() ? ` Developer mode lets it run on the ${where}.` : '';
    if (this.#validation === null && this.#validationUsedBy === JSON.stringify(this.state.document)) return `${VALIDATION_USED}${override}`;
    if (this.#validation === null) return `Not validated: validate before running on the robot.${override}`;
    return `${this.#validation.sceneChanged ? 'Scene' : 'Plan'} changed since its validation: validate again.${override}`;
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
    const stale = !this.#world.published && this.#postureStale !== null ? new Set([edited]) : new Set();
    this.#parts.posture.hidden = stale.size === 0;
    showText(this.#parts.posture, stale.size === 0 ? '' : `${this.#postureStale} — the picture may not match the robot.`);
    this.#scene.show(this.state, { objects: this.#world.objects, robots, postures, colors: this.#perceivedColors(), stale }, this.#overlay());
    const shown = viewMode({ published: this.#world.published, mode: this.#run[RunStatusKey.MODE] ?? null, real: this.#robotExecutor() === ExecutorKind.REAL, mirroring: this.#mirroring });
    showText(this.#parts.viewMode, shown.text);
    this.#parts.viewMode.dataset.mode = shown.mode;
  }

  /**
   * @returns {HTMLElement} The folded legend of the 3D view: what each kind of mark
   *   means, in its colour.
   */
  #legend() {
    const elements = this.#elements;
    const list = elements.create('ul');
    for (const entry of LEGEND) {
      const swatch = elements.create('span', 'legend-swatch');
      swatch.dataset.shape = entry.shape;
      swatch.style.color = entry.color;
      swatch.setAttribute('aria-hidden', 'true');
      const item = elements.create('li');
      item.append(swatch, entry.label);
      list.append(item);
    }
    const legend = elements.create('details', 'scene-legend');
    legend.append(elements.create('summary', '', 'Legend'), list);
    return legend;
  }

  /**
   * @returns {Map<string, string>} The color each object a run perceived shows, by the
   *   object's identity, which the 3D view tints it with.
   */
  #perceivedColors() {
    if (!this.#runShown) return new Map();
    const progress = this.#progress();
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
    parts.task.placeholder = TASK_HINT.PLACEHOLDER;
    parts.task.title = TASK_HINT.TITLE;
    parts.environment = new EnvironmentView(document, this);
    parts.saved = this.#choice(PlanAction.OPEN, this.#planChoices(), OPEN_PROMPT.value, (value) => {
      const label = this.#planChoices().find((choice) => choice.value === value)?.label ?? value;
      this.#replacePlan(`opening the saved plan “${label}”`, () => {
        this.#forgetRun();
        this.#open(value).then(() => this.render());
      });
    });
    const bar = elements.create('header', 'bar builder-bar');
    const plansRow = elements.create('div', 'button-row');
    parts.newPlan = elements.button('New', PlanAction.NEW, () => this.#replacePlan('a new plan', () => this.#newPlan()));
    parts.save = elements.button('Save', PlanAction.SAVE, () => this.#save());
    parts.undo = elements.button('Undo', PlanAction.UNDO, () => this.undo());
    parts.redo = elements.button('Redo', PlanAction.REDO, () => this.redo());
    plansRow.append(parts.newPlan, parts.saved, parts.save, parts.undo, parts.redo);
    if ((this.state.catalog[PlanBuilderCatalogKey.TEMPLATES] ?? []).length > 0) {
      parts.templates = this.#choice(PlanAction.NEW_FROM_TEMPLATE, this.#templateChoices(), TEMPLATE_PROMPT.value, (value) => {
        const label = this.#templateChoices().find((choice) => choice.value === value)?.label ?? value;
        parts.templates.value = TEMPLATE_PROMPT.value;
        this.#replacePlan(`the template “${label}”`, () => this.#newFromTemplate(value));
      });
      plansRow.append(parts.templates);
    }
    if (this.state.skills().length > 0) {
      parts.developer = elements.input('checkbox', PlanAction.DEVELOPER_MODE, () => this.#setDeveloperMode(parts.developer.checked));
      parts.developer.checked = this.state.developerMode();
      plansRow.append(elements.label('developer mode', parts.developer));
    }
    parts.replaceText = elements.create('span');
    parts.replacePlan = elements.button('Replace and lose the changes', PlanAction.REPLACE_PLAN, () => this.#settleReplace(true));
    parts.keepPlan = elements.button('Keep editing', PlanAction.KEEP_PLAN, () => this.#settleReplace(false));
    parts.replaceConfirm = elements.create('div', 'replace-confirm');
    parts.replaceConfirm.setAttribute('role', 'alert');
    parts.replaceConfirm.hidden = true;
    parts.replaceConfirm.append(parts.replaceText, parts.keepPlan, parts.replacePlan);
    elements.listen(parts.replaceConfirm, DomEvent.KEY_DOWN, (event) => this.#confirmKey(event));
    bar.append(elements.create('strong', 'builder-title', 'Plan builder'), elements.label('name', parts.name), elements.label('task', parts.task), plansRow, parts.replaceConfirm);

    parts.robots = new RobotsView(document, this);
    parts.steps = new StepsView(document, this);
    parts.objects = new ObjectsView(document, this);
    parts.constraints = new ConstraintsView(document, this, new ConstraintSentences(this.state.catalog[PlanBuilderCatalogKey.CONSTRAINT_RULES], this.#environment.storage));
    const side = elements.create('aside', 'builder-side');
    side.append(
      this.#section('Environment', parts.environment.element),
      this.#section('Robots', parts.robots.element, 'Choose a robot, here or in the 3D view, to edit its plan.'),
      this.#section('Actions', parts.steps.palette, 'Click or drag an action into the plan.'),
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

    parts.stage = elements.button(RUN_LABELS[RunMode.STAGE], PlanAction.STAGE, () => this.#start(RunMode.STAGE));
    parts.perform = elements.button(RUN_LABELS[RunMode.PERFORM], PlanAction.PERFORM, () => this.#start(RunMode.PERFORM));
    parts.simulate = elements.button(RUN_LABELS[RunMode.SIMULATE], PlanAction.SIMULATE, () => this.#start(RunMode.SIMULATE));
    parts.validate = elements.button('Validate', PlanAction.VALIDATE, () => this.validate());
    parts.validate.dataset.hint = 'Tries every step in a copy of the twin; nothing moves.';
    parts.scan = elements.button('Scan scene', PlanAction.SCAN_SCENE, () => this.scanScene());
    parts.scan.dataset.hint = 'Fills the plan\'s objects with what the robot sees on its table.';
    const executors = this.state.catalog[PlanBuilderCatalogKey.PROFILE]?.[RobotProfileKey.EXECUTORS] ?? {};
    if (executors[RunMode.STAGE] !== ExecutorKind.REAL) parts.stage.dataset.hint = STAGE_TITLE;
    for (const [mode, button] of [[RunMode.PERFORM, parts.perform], [RunMode.SIMULATE, parts.simulate]]) {
      const hint = EXECUTOR_TITLES[executors[mode] ?? DEFAULT_EXECUTORS[mode]];
      if (hint) button.dataset.hint = hint;
    }
    const robotExecutor = this.#robotExecutor();
    const onRealRobot = robotExecutor === ExecutorKind.REAL;
    parts.robot = elements.button(onRealRobot ? 'Run on the real robot' : 'Run on robot', PlanAction.RUN_ON_ROBOT, () => this.#runOnRobot());
    parts.robot.hidden = robotExecutor === null;
    if (onRealRobot) {
      parts.robot.classList.add('real-robot');
      parts.robot.dataset.hint = 'Moves the real robot. Runs a plan that passed its validation against where the robot stands now; keep the emergency stop at hand.';
    }
    parts.stop = elements.button('Stop', PlanAction.STOP, () => this.#stop());
    parts.capture = elements.button('Capture live poses', PlanAction.CAPTURE, () => this.#capture());
    // the live scene to capture from is a simulated one, whose poses do not belong in a plan for the real robot
    parts.capture.hidden = onRealRobot;
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
    // the flow in its order first, then the simulated runs, the tools, and apart from them all the run on the robot
    const flowRow = elements.create('div', 'button-row flow-actions');
    const runtimeCheck = elements.create('span', 'runtime-check', LENIENT_CHECK.LABEL);
    runtimeCheck.title = LENIENT_CHECK.TITLE;
    runtimeCheck.hidden = this.state.catalog[PlanBuilderCatalogKey.PROFILE]?.[RobotProfileKey.PERCEPTION]?.[PerceptionSettingsKey.RUNTIME_CHECK] !== RuntimeCheck.LENIENT;
    flowRow.append(parts.scan, parts.validate, parts.stop, runtimeCheck);
    const simulatedRow = elements.create('div', 'button-row');
    simulatedRow.append(parts.stage, parts.perform, parts.simulate);
    const toolRow = elements.create('div', 'button-row tool-actions');
    toolRow.append(
      parts.capture,
      turn,
      elements.button('Look at the plan', PlanAction.FRAME, () => this.#scene?.frameMarkers()),
      elements.button('Show demo', PlanAction.SHOW_DEMO, () => this.#showDemo()),
      elements.button('Write demo', PlanAction.WRITE_DEMO, () => this.#writeDemo()),
    );
    for (const button of toolRow.children) button.title = TOOL_TITLES[button.dataset.action];
    const robotRow = elements.create('div', ROBOT_RUN_ROW);
    robotRow.hidden = parts.robot.hidden;
    if (onRealRobot) robotRow.append(elements.create('span', 'robot-actions-label', REAL_MOTION));
    robotRow.append(parts.robot);
    const runRow = elements.create('div', 'run-row');
    runRow.append(flowRow, simulatedRow, toolRow, robotRow);
    parts.runState = elements.create('span', 'run-state');
    parts.elapsed = elements.create('span', 'flow-elapsed');
    parts.flow = elements.create('div', 'flow-status');
    parts.flow.setAttribute('role', 'status');
    const indicator = elements.create('span', 'flow-indicator');
    indicator.setAttribute('aria-hidden', 'true');
    parts.flow.append(indicator, parts.runState, parts.elapsed);
    parts.validationState = elements.create('span', 'validation-state');
    parts.message = elements.create('span', 'message');
    parts.posture = elements.create('span', 'run-state posture-state');
    parts.posture.dataset.state = RunState.FAILED;
    parts.posture.hidden = true;
    parts.log = elements.create('pre', 'run-log');
    parts.output = elements.create('pre', 'demo-source');
    parts.output.hidden = true;
    const stage = elements.create('div', 'builder-stage');
    const controls = elements.create('div', 'builder-controls');
    const lines = elements.create('div', 'status-row');
    lines.append(parts.validationState, parts.posture, parts.message);
    controls.append(parts.safety, parts.flow, runRow, lines, statusLine);
    const output = elements.create('div', 'builder-output');
    parts.logDetails = this.#details('Run output', parts.log);
    parts.scanFigures = elements.create('div');
    parts.scanImages = this.#details('What the scan saw', parts.scanFigures);
    parts.scanImages.className = 'scan-images';
    parts.scanImages.hidden = true;
    output.append(parts.logDetails, parts.scanImages, this.#details('Generated demo', parts.output));
    const view = elements.create('section', 'builder-view');
    view.append(controls, stage, output);
    const main = elements.create('div', 'builder-main');
    main.append(side, planColumn, view);
    // the flow sits after the side panel and the steps; the keyboard reaches it first
    const skip = elements.button('Skip to Scan scene, Validate, Run and Stop', PlanAction.SKIP_TO_FLOW, () => this.#focusFlow(flowRow));
    skip.className = 'skip-link';
    this.#root.replaceChildren(skip, bar, main);
    if (this.#environment.createScene) {
      parts.viewMode = elements.create('span', 'scene-mode');
      stage.append(parts.viewMode, this.#legend());
      this.#scene = this.#environment.createScene(
        stage,
        new PlanSceneListeners(
          (selection) => {
            parts.selection = selection;
            parts.objects.render(selection?.kind === MarkerKind.OBJECT ? selection.identifier : null);
            const robot = selection?.kind === MarkerKind.ROBOT ? selection.identifier : null;
            if (robot && robot !== this.state.activeRobot()?.[PlannedRobotKey.IDENTIFIER] && this.lockedByRun() === null) this.edit(() => this.state.selectRobot(robot));
          },
          (selection, pose) => this.#placed(selection, pose),
          (error) => this.report(error.message, Tone.ERROR),
          (selection, pose) => (selection.kind === MarkerKind.TARGET ? this.movingMarker(selection, pose) : null),
        ),
      );
    } else {
      stage.append(elements.create('p', 'empty', 'This browser cannot show the 3D view; the plan can still be composed.'));
    }
  }

  /**
   * Focus the first flow button that may be pressed now, which during a run is Stop,
   * else the row holding them.
   * @param {HTMLElement} flowRow The row of the flow buttons.
   */
  #focusFlow(flowRow) {
    const parts = this.#parts;
    const button = [parts.scan, parts.validate, parts.robot, parts.stop].find((candidate) => !candidate.disabled && !candidate.hidden);
    if (button) {
      button.focus();
      return;
    }
    flowRow.tabIndex = -1;
    flowRow.focus();
  }

  /**
   * A select whose choice is taken only when the person makes it: picked with the
   * mouse or opened list, or browsed to with the arrow keys and taken with Enter, which
   * a browser changing the value at every arrow key would take at once otherwise.
   * @param {string} action The select's `PlanAction` value.
   * @param {Array<{value: string, label: string}>} options The options; the one with
   *   the empty value chooses nothing.
   * @param {string} value The value selected.
   * @param {function(string): void} choose Called with the chosen value.
   * @returns {HTMLSelectElement} The select.
   */
  #choice(action, options, value, choose) {
    const elements = this.#elements;
    let browsing = false;
    const select = elements.select(action, options, value, (chosen) => {
      if (!browsing && chosen) choose(chosen);
    });
    elements.listen(select, DomEvent.KEY_DOWN, (event) => {
      if (event.key === CHOOSING_KEY) {
        browsing = false;
        select.title = '';
        if (select.value) choose(select.value);
      } else if (!event.altKey && !event.ctrlKey && !event.metaKey && (BROWSING_KEYS.includes(event.key) || /^\S$/u.test(event.key))) {
        browsing = true;
        select.title = BROWSING_HINT;
      }
    });
    elements.listen(select, DomEvent.MOUSE_DOWN, () => {
      browsing = false;
      select.title = '';
    });
    elements.listen(select, DomEvent.BLUR, () => {
      if (!browsing) return;
      browsing = false;
      select.title = '';
      select.value = '';
    });
    return select;
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
