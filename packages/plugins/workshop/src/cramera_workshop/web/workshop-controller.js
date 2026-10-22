/**
 * The Workshop panel's commands to the contact world: one at a time, in order, each
 * answered with the measured state the scene then shows. Spring targets are what the
 * panel sends; where bodies end up is what MuJoCo measures.
 */

import {
  DrawerKey,
  DriveDirection,
  ThreadKey,
  ThreadState,
  WorkshopAction,
  WorkshopBodyKey,
  WorkshopCommandKey,
  WorkshopKey,
  WorkshopPartKind,
  WorkshopStateKey,
} from '../../protocol.js';
import { QUATERNION_START, rotated, separation, shifted, zAxis } from './pose-math.js';

/**
 * The steps and limits of the panel's manipulation.
 */
export const Manipulation = Object.freeze({
  /** How often the state is read while the panel is shown, in milliseconds. */
  POLL_MILLISECONDS: 100,
  /** How far one move button shifts the spring target, in metres. */
  MOVE_STEP: 0.025,
  /** How far one tilt button turns the spring target, in radians. */
  ANGLE_STEP: Math.PI / 12,
  /** The decimals a shifted target keeps, so repeated steps do not drift. */
  TARGET_DECIMALS: 6,
  /** The height bodies are carried at when the workshop names none, in metres. */
  CLEARANCE: 1.3,
  /** How far along its axis a screw or driver approaches its goal, in metres. */
  APPROACH_CLEARANCE: 0.15,
  /** The lift above a goal before travelling to it, in metres. */
  GOAL_CLEARANCE: 0.1,
  /** How close to vertical an approach axis counts as vertical. */
  AXIS_TOLERANCE: 1e-6,
  /** How close a body must come to a travel waypoint, in metres. */
  POSITION_TOLERANCE: 0.006,
  /** How close a body's orientation must come to a travel waypoint, in radians. */
  ANGLE_TOLERANCE: 0.08,
  /** How close a body must come to its final goal, in metres. */
  FINAL_POSITION_TOLERANCE: 0.0015,
  /** How close a body's orientation must come to its final goal, in radians. */
  FINAL_ANGLE_TOLERANCE: 0.04,
  /** How long a body may take to reach a waypoint, in milliseconds. */
  WAYPOINT_TIMEOUT_MILLISECONDS: 8000,
  /** How long the thread may take to report a capture or contact, in milliseconds. */
  CONTACT_TIMEOUT_MILLISECONDS: 2000,
});

/**
 * What an alignment brings to the pilot hole.
 */
export const AlignmentKind = Object.freeze({
  /** The selected screw, to the pilot hole's entrance. */
  SCREW: 'screw',
  /** The screwdriver, into the seated screw's slot. */
  DRIVER: 'driver',
});

/**
 * How closely a waypoint must be reached.
 */
const Waypoint = Object.freeze({
  /** Straight up from where the body is; its orientation does not matter yet. */
  LIFT: 'lift',
  /** On the way; the travel tolerances apply. */
  TRANSIT: 'transit',
  /** The goal; the final tolerances apply. */
  FINAL: 'final',
});

/**
 * The thread phases in which a screw sits in the pilot hole.
 */
const SEATED_PHASES = Object.freeze([ThreadState.SEATED, ThreadState.DRIVING, ThreadState.STOPPED, ThreadState.LIMIT]);

/**
 * What the panel tells the user.
 */
export const WorkshopMessage = Object.freeze({
  CONNECTING: 'Connecting to MuJoCo…',
  RUNNING: 'MuJoCo running. Grab an object to lift and tilt it.',
  PAUSED: 'Physics paused. Resume to continue.',
  RESET: 'Workshop reset.',
  RELEASED: 'Released. Gravity and contacts move the object.',
  HELD: 'held by a spring. Lift or tilt it with the controls.',
  TARGET_MOVED: 'Spring target moved. Contacts may stop the object.',
  GRAB_FIRST: 'Start physics and grab an object first.',
  DRAWER_MOVED: 'Drawer motor target changed. Contacts may stop it.',
  UNKNOWN_DRAWER: 'Unknown drawer.',
  DRIVING: 'Driver turning. The thread follows its measured rotation.',
  DRIVER_STOPPED: 'Driver stopped.',
  BUSY: 'Finish the current manipulation first.',
  SELECT_SCREW: 'Select a screw before positioning it.',
  ALIGNMENT_STOPPED: 'Alignment stopped.',
  TARGET_MISSING: 'The physics alignment target is unavailable.',
  BLOCKED: 'Alignment blocked: the object did not reach its target. Move the obstruction or lift it by hand.',
  DRIVER_CONTACT: 'Driver contact confirmed. Drive in or reverse.',
  SCREW_SEATED: 'Screw seated in the pilot hole. Align the driver next.',
  NO_DRIVER_CONTACT: 'Driver contact was not confirmed. Adjust its alignment before driving.',
  NO_CAPTURE: 'The pilot hole did not capture the screw. Reposition it before continuing.',
  VIEW_CHANGED: 'View changed.',
  VIEW_MISSING: 'View unavailable.',
  CLOSED: 'Controls closed.',
});

// %% outcome

/**
 * What a command or a manipulation came to.
 */
export class Outcome {
  /**
   * @param {boolean} ok Whether it succeeded.
   * @param {string} message What to tell the user.
   */
  constructor(ok, message) {
    /**
     * Whether it succeeded.
     * @type {boolean}
     */
    this.ok = ok;
    /**
     * What to tell the user.
     * @type {string}
     */
    this.message = message;
  }
}

/**
 * The clock the controller waits with; replaced in tests.
 */
export class WallClock {
  /**
   * @returns {number} The current time, in milliseconds.
   */
  now() {
    return Date.now();
  }

  /**
   * @param {number} milliseconds How long to wait.
   * @returns {Promise<void>} Settles after that time.
   */
  wait(milliseconds) {
    return new Promise((resolve) => setTimeout(resolve, milliseconds));
  }
}

// %% controller

export class WorkshopController {
  /**
   * The workshop description of the shown bundle.
   * @type {Object}
   */
  #workshop;

  /**
   * The scene the measured state is shown on.
   * @type {import('./workshop-scene.js').WorkshopScene}
   */
  #scene;

  /**
   * The workshop routes.
   * @type {import('./workshop-client.js').WorkshopClient}
   */
  #client;

  /**
   * Waits between state reads during an alignment.
   * @type {WallClock}
   */
  #clock;

  /**
   * The command the next one waits for.
   * @type {Promise<Outcome>}
   */
  #queue = Promise.resolve(new Outcome(true, ''));

  /**
   * Counts commands, so a state read sent before one is not shown after it.
   * @type {number}
   */
  #revision = 0;

  /**
   * Counts alignments, so a newer command stops an older alignment.
   * @type {number}
   */
  #alignmentRevision = 0;

  /**
   * Whether a state read is under way.
   * @type {boolean}
   */
  #polling = false;

  /**
   * The display name of each movable body by object key.
   * @type {Map<string, string>}
   */
  labels = new Map();

  /**
   * The object key of the body the panel works with.
   * @type {string|null}
   */
  selected = null;

  /**
   * The last measured state, or null before the first answer.
   * @type {Object|null}
   */
  state = null;

  /**
   * The spring target the panel last sent, or null.
   * @type {Array<number>|null}
   */
  target = null;

  /**
   * How many commands are under way.
   * @type {number}
   */
  pending = 0;

  /**
   * Whether an alignment is under way.
   * @type {boolean}
   */
  aligning = false;

  /**
   * Why the workshop is unavailable, or null.
   * @type {string|null}
   */
  error = null;

  /**
   * What the panel tells the user.
   * @type {string}
   */
  message = WorkshopMessage.CONNECTING;

  /**
   * Whether the panel was closed.
   * @type {boolean}
   */
  closed = false;

  /**
   * Called whenever what the panel shows changed.
   * @type {function(): void}
   */
  onChange = () => {};

  /**
   * @param {Object} workshop The workshop description of the shown bundle.
   * @param {import('./workshop-scene.js').WorkshopScene} scene The shown scene.
   * @param {import('./workshop-client.js').WorkshopClient} client The workshop routes.
   * @param {WallClock=} clock Waits between state reads during an alignment.
   */
  constructor(workshop, scene, client, clock = new WallClock()) {
    this.#workshop = workshop;
    this.#scene = scene;
    this.#client = client;
    this.#clock = clock;
    const bodies = [
      ...(workshop[WorkshopKey.PARTS] ?? []),
      ...(workshop[WorkshopKey.BINS] ?? []),
      workshop[WorkshopKey.ASSEMBLY],
      workshop[WorkshopKey.DRIVER],
    ].filter(Boolean);
    for (const body of bodies) this.labels.set(body[WorkshopBodyKey.KEY], body[WorkshopBodyKey.LABEL]);
    this.selected = this.labels.keys().next().value ?? null;
  }

  // %% state

  /**
   * @returns {boolean} Whether the contact world answered and takes commands.
   */
  isReady() {
    return !this.closed && this.error === null && this.state !== null;
  }

  /**
   * @returns {boolean} Whether time passes in the contact world.
   */
  isRunning() {
    return this.isReady() && this.state[WorkshopStateKey.RUNNING] === true;
  }

  /**
   * @returns {boolean} Whether the spring holds a body and no alignment is under way.
   */
  canManipulate() {
    return this.isRunning() && !this.aligning && Boolean(this.held());
  }

  /**
   * @returns {string|null} The object key of the body the spring holds.
   */
  held() {
    return this.state?.[WorkshopStateKey.HELD] ?? null;
  }

  /**
   * @param {string} key An object key.
   * @returns {string} The body's display name.
   */
  label(key) {
    return this.labels.get(key) ?? key;
  }

  /**
   * @param {string} key The object key of a movable body.
   * @returns {boolean} Whether the body became the selected one.
   */
  select(key) {
    if (!this.labels.has(key)) return false;
    this.selected = key;
    this.onChange();
    return true;
  }

  /**
   * Show a measured state.
   * @param {Object} state The workshop's measured state.
   */
  accept(state) {
    if (this.closed) return;
    this.state = state;
    this.error = state[WorkshopStateKey.AVAILABLE] === false ? state[WorkshopStateKey.ERROR] ?? WorkshopMessage.CLOSED : null;
    this.#scene.show(state);
    this.onChange();
  }

  /**
   * @param {Error} error Why a request failed.
   * @returns {Outcome} The failure.
   */
  fail(error) {
    if (this.closed) return new Outcome(false, WorkshopMessage.CLOSED);
    this.message = error.reason ?? error.message;
    this.onChange();
    return new Outcome(false, this.message);
  }

  /**
   * Read the state unless a command is under way.
   * @returns {Promise<void>} Settles once the state is shown.
   */
  async poll() {
    if (this.closed || this.#polling || this.pending) return;
    this.#polling = true;
    const revision = this.#revision;
    const answer = await this.#client.state().then(
      (state) => ({ state }),
      (error) => ({ error }),
    );
    this.#polling = false;
    if (revision !== this.#revision) return;
    if (answer.error) this.fail(answer.error);
    else this.accept(answer.state);
  }

  // %% commands

  /**
   * Send a command after the commands before it.
   * @param {Object} command A workshop command document.
   * @param {string} message What to tell the user when it succeeds.
   * @returns {Promise<Outcome>} What it came to.
   */
  command(command, message) {
    this.#revision += 1;
    this.pending += 1;
    this.onChange();
    const outcome = this.#queue.then(async () => {
      if (this.closed) return new Outcome(false, WorkshopMessage.CLOSED);
      const answer = await this.#client.command(command).then(
        (state) => ({ state }),
        (error) => ({ error }),
      );
      if (answer.error) return this.fail(answer.error);
      this.message = message;
      this.accept(answer.state);
      return new Outcome(this.error === null, this.error ?? message);
    });
    this.#queue = outcome.finally(() => {
      this.pending -= 1;
      this.onChange();
    });
    return outcome;
  }

  /**
   * @returns {Promise<Outcome>} Time passes in the contact world, built on the first start.
   */
  start() {
    this.#scene.pausePlayback();
    return this.command({ [WorkshopCommandKey.ACTION]: WorkshopAction.START }, WorkshopMessage.RUNNING);
  }

  /**
   * @returns {Promise<Outcome>} Time stops and the held body is let go.
   */
  pause() {
    this.#alignmentRevision += 1;
    return this.command({ [WorkshopCommandKey.ACTION]: WorkshopAction.PAUSE }, WorkshopMessage.PAUSED);
  }

  /**
   * @returns {Promise<Outcome>} Every body is back where it started.
   */
  reset() {
    this.#alignmentRevision += 1;
    this.target = null;
    return this.command({ [WorkshopCommandKey.ACTION]: WorkshopAction.RESET }, WorkshopMessage.RESET);
  }

  /**
   * @returns {Promise<Outcome>} The held body is let go.
   */
  release() {
    this.#alignmentRevision += 1;
    this.target = null;
    return this.command({ [WorkshopCommandKey.ACTION]: WorkshopAction.RELEASE }, WorkshopMessage.RELEASED);
  }

  /**
   * @param {string=} key The object key of the body to hold; the selected one by default.
   * @returns {Promise<Outcome>} The spring holds the body where it is.
   */
  async grab(key = this.selected) {
    if (!this.isRunning() || !this.labels.has(key)) return new Outcome(false, WorkshopMessage.GRAB_FIRST);
    this.select(key);
    const outcome = await this.command(
      { [WorkshopCommandKey.ACTION]: WorkshopAction.GRAB, [WorkshopCommandKey.OBJECT]: key },
      `${this.label(key)} ${WorkshopMessage.HELD}`,
    );
    if (outcome.ok) this.target = this.state[WorkshopStateKey.OBJECTS][key].slice();
    return outcome;
  }

  /**
   * @param {Array<number>} pose The held body's new spring target.
   * @returns {Promise<Outcome>} The target moved; contacts may stop the body.
   */
  moveTo(pose) {
    const held = this.held();
    if (!this.isRunning() || !held || pose.length !== 7 || !pose.every(Number.isFinite)) {
      return Promise.resolve(new Outcome(false, WorkshopMessage.GRAB_FIRST));
    }
    this.target = pose.slice();
    return this.command(
      { [WorkshopCommandKey.ACTION]: WorkshopAction.MOVE, [WorkshopCommandKey.OBJECT]: held, [WorkshopCommandKey.POSE]: this.target.slice() },
      WorkshopMessage.TARGET_MOVED,
    );
  }

  /**
   * @returns {Array<number>|null} The target the next move starts from.
   */
  #currentTarget() {
    return this.target ?? this.state?.[WorkshopStateKey.OBJECTS]?.[this.held()] ?? null;
  }

  /**
   * @param {Array<number>} offset How far to shift the target, in metres.
   * @returns {Promise<Outcome>} The target moved.
   */
  moveBy(offset) {
    const pose = this.#currentTarget();
    if (!pose) return Promise.resolve(new Outcome(false, WorkshopMessage.GRAB_FIRST));
    return this.moveTo(shifted(pose, offset, Manipulation.TARGET_DECIMALS));
  }

  /**
   * @param {number} axis 0, 1 or 2 for the world's x, y or z axis.
   * @param {number} angle How far to turn the target, in radians.
   * @returns {Promise<Outcome>} The target turned.
   */
  tilt(axis, angle) {
    const pose = this.#currentTarget();
    if (!pose) return Promise.resolve(new Outcome(false, WorkshopMessage.GRAB_FIRST));
    return this.moveTo(rotated(pose, axis, angle));
  }

  /**
   * @param {Object} drawer A drawer of the workshop description.
   * @param {number} position The drawer motor's target, in metres.
   * @returns {Promise<Outcome>} The motor's target changed.
   */
  setDrawer(drawer, position) {
    return this.command(
      { [WorkshopCommandKey.ACTION]: WorkshopAction.DRAWER, [WorkshopCommandKey.JOINT]: drawer[DrawerKey.JOINT], [WorkshopCommandKey.POSITION]: position },
      WorkshopMessage.DRAWER_MOVED,
    );
  }

  /**
   * @param {string} direction A `DriveDirection` value.
   * @returns {Promise<Outcome>} The held driver turns or stops.
   */
  drive(direction) {
    return this.command(
      { [WorkshopCommandKey.ACTION]: WorkshopAction.DRIVE, [WorkshopCommandKey.DIRECTION]: direction },
      direction === DriveDirection.STOP ? WorkshopMessage.DRIVER_STOPPED : WorkshopMessage.DRIVING,
    );
  }

  // %% alignment

  /**
   * Bring the selected screw to the pilot hole, or the driver into the seated screw's
   * slot: lift clear of the fixtures, travel above the goal, come down along its axis.
   * @param {string} kind An `AlignmentKind` value.
   * @returns {Promise<Outcome>} Whether the thread captured the screw or the blade engaged.
   */
  async align(kind) {
    if (!this.isRunning() || this.aligning) return new Outcome(false, WorkshopMessage.BUSY);
    const driver = this.#workshop[WorkshopKey.DRIVER]?.[WorkshopBodyKey.KEY];
    const key = kind === AlignmentKind.DRIVER ? driver : this.selected;
    if (kind !== AlignmentKind.DRIVER && !this.#isScrew(key)) return new Outcome(false, WorkshopMessage.SELECT_SCREW);
    this.aligning = true;
    const revision = ++this.#alignmentRevision;
    this.onChange();
    const outcome = await this.#alignBody(kind, key, revision);
    this.aligning = false;
    this.onChange();
    return outcome;
  }

  /**
   * @param {string} key An object key.
   * @returns {boolean} Whether the workshop describes the body as a screw.
   */
  #isScrew(key) {
    return (this.#workshop[WorkshopKey.PARTS] ?? []).some(
      (part) => part[WorkshopBodyKey.KEY] === key && part[WorkshopBodyKey.KIND] === WorkshopPartKind.SCREW,
    );
  }

  /**
   * @param {string} kind An `AlignmentKind` value.
   * @param {string} key The body to bring.
   * @param {number} revision The alignment's revision.
   * @returns {Promise<Outcome>} What it came to.
   */
  async #alignBody(kind, key, revision) {
    let outcome = await this.grab(key);
    if (!outcome.ok) return outcome;
    const thread = this.state[WorkshopStateKey.THREAD] ?? {};
    const goal = kind === AlignmentKind.DRIVER ? thread[ThreadKey.DRIVER_TARGET_POSE] : thread[ThreadKey.SCREW_TARGET_POSE];
    if (!goal) return new Outcome(false, WorkshopMessage.TARGET_MISSING);
    for (const [waypoint, phase] of this.#waypoints(key, goal)) {
      if (revision !== this.#alignmentRevision) return new Outcome(false, WorkshopMessage.ALIGNMENT_STOPPED);
      outcome = await this.moveTo(waypoint);
      if (!outcome.ok) return outcome;
      outcome = await this.#reach(key, waypoint, revision, phase);
      if (!outcome.ok) return outcome;
    }
    if (kind === AlignmentKind.DRIVER) return this.#awaitThread(kind, key, revision);
    outcome = await this.release();
    if (!outcome.ok) return outcome;
    return this.#awaitThread(kind, key, this.#alignmentRevision);
  }

  /**
   * @param {string} key The body to bring.
   * @param {Array<number>} goal Its goal pose.
   * @returns {Array<Array>} Each waypoint with how closely it must be reached.
   */
  #waypoints(key, goal) {
    const actual = this.state[WorkshopStateKey.OBJECTS][key];
    const height = Math.max(
      this.#workshop[WorkshopKey.LIFT_HEIGHT] ?? Manipulation.CLEARANCE,
      actual[2],
      goal[2] + Manipulation.GOAL_CLEARANCE,
    );
    const raised = actual.slice();
    raised[2] = height;
    const axis = zAxis(goal.slice(QUATERNION_START));
    const clearance = axis[2] > 1 - Manipulation.AXIS_TOLERANCE
      ? Math.max(Manipulation.APPROACH_CLEARANCE, height - goal[2])
      : Manipulation.APPROACH_CLEARANCE;
    const approach = goal.map((value, index) => (index < 3 ? value + axis[index] * clearance : value));
    const above = approach.slice();
    above[2] = Math.max(height, approach[2]);
    const waypoints = [[raised, Waypoint.LIFT], [above, Waypoint.TRANSIT]];
    if (Math.abs(above[2] - approach[2]) > Manipulation.AXIS_TOLERANCE) waypoints.push([approach, Waypoint.TRANSIT]);
    waypoints.push([goal, Waypoint.FINAL]);
    return waypoints;
  }

  /**
   * Wait until the measured body reaches a waypoint; stop at a blocked one.
   * @param {string} key The body.
   * @param {Array<number>} desired The waypoint.
   * @param {number} revision The alignment's revision.
   * @param {string} phase A `Waypoint` value.
   * @returns {Promise<Outcome>} Whether the body got there in time.
   */
  async #reach(key, desired, revision, phase) {
    const final = phase === Waypoint.FINAL;
    const positionTolerance = final ? Manipulation.FINAL_POSITION_TOLERANCE : Manipulation.POSITION_TOLERANCE;
    const angleTolerance = final ? Manipulation.FINAL_ANGLE_TOLERANCE : Manipulation.ANGLE_TOLERANCE;
    const deadline = this.#clock.now() + Manipulation.WAYPOINT_TIMEOUT_MILLISECONDS;
    while (this.#clock.now() < deadline) {
      if (!this.isRunning() || revision !== this.#alignmentRevision || this.held() !== key) {
        return new Outcome(false, WorkshopMessage.ALIGNMENT_STOPPED);
      }
      const { distance, angle } = separation(this.state[WorkshopStateKey.OBJECTS][key], desired);
      if (distance <= positionTolerance && (phase === Waypoint.LIFT || angle <= angleTolerance)) return new Outcome(true, '');
      await this.#clock.wait(Manipulation.POLL_MILLISECONDS);
      await this.poll();
    }
    return new Outcome(false, WorkshopMessage.BLOCKED);
  }

  /**
   * Wait until the thread reports the screw captured or the blade engaged.
   * @param {string} kind An `AlignmentKind` value.
   * @param {string} key The screw or driver.
   * @param {number} revision The alignment's revision.
   * @returns {Promise<Outcome>} Whether the thread confirmed it in time.
   */
  async #awaitThread(kind, key, revision) {
    const deadline = this.#clock.now() + Manipulation.CONTACT_TIMEOUT_MILLISECONDS;
    while (this.#clock.now() < deadline) {
      if (!this.isRunning() || revision !== this.#alignmentRevision) return new Outcome(false, WorkshopMessage.ALIGNMENT_STOPPED);
      const thread = this.state[WorkshopStateKey.THREAD] ?? {};
      if (kind === AlignmentKind.DRIVER && thread[ThreadKey.ENGAGED]) return new Outcome(true, WorkshopMessage.DRIVER_CONTACT);
      if (kind !== AlignmentKind.DRIVER && thread[ThreadKey.SCREW] === key && SEATED_PHASES.includes(thread[ThreadKey.STATE])) {
        return new Outcome(true, WorkshopMessage.SCREW_SEATED);
      }
      await this.#clock.wait(Manipulation.POLL_MILLISECONDS);
      await this.poll();
    }
    return new Outcome(false, kind === AlignmentKind.DRIVER ? WorkshopMessage.NO_DRIVER_CONTACT : WorkshopMessage.NO_CAPTURE);
  }

  // %% views and closing

  /**
   * @param {string} name A `WorkshopView` value.
   * @returns {Outcome} Whether the workshop has that view.
   */
  look(name) {
    const view = this.#workshop[WorkshopKey.CAMERAS]?.[name];
    if (!view) return new Outcome(false, WorkshopMessage.VIEW_MISSING);
    this.#scene.look(view);
    return new Outcome(true, WorkshopMessage.VIEW_CHANGED);
  }

  /**
   * Stop showing states; let go of a body the panel holds, after the commands under way.
   * @returns {Promise<Outcome>} Settles once the release was sent.
   */
  close() {
    const holding = this.held() !== null;
    this.closed = true;
    this.#revision += 1;
    this.onChange = () => {};
    if (!holding) return this.#queue;
    this.#queue = this.#queue.then(() =>
      this.#client.command({ [WorkshopCommandKey.ACTION]: WorkshopAction.RELEASE }).then(
        () => new Outcome(true, ''),
        (error) => new Outcome(false, error.message),
      ),
    );
    return this.#queue;
  }
}
