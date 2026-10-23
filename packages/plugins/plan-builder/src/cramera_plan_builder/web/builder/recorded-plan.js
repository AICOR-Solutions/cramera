/**
 * The plans a recording performed, as steps: each plan's outermost actions, with the
 * frames each ran in, so the step at any frame of the replay is known.
 */

import { DeclaredFieldKey, PlanNodeKey, PlanNodeKind, PoseValueKey } from '../../../protocol.js';

/**
 * Where a step is at a frame of the replay.
 */
export const StepPhase = Object.freeze({
  WAITING: 'waiting',
  RUNNING: 'running',
  DONE: 'done',
});

/**
 * The end of an action's class name, which its name in words leaves out.
 */
const ACTION_SUFFIX = 'Action';

/**
 * Where a new word of a class name starts.
 */
const WORD_BOUNDARY = /(?<=[a-z0-9])(?=[A-Z])/;

/**
 * The recorded fields a step's card shows when the recording does not name the fields
 * of the step's action, in order.
 */
const SHOWN_FIELDS = Object.freeze([PlanNodeKey.ARM, PlanNodeKey.TARGET]);

/**
 * Separates the words of an action field's name.
 */
const FIELD_NAME_SEPARATOR = '_';

/**
 * How a field left at its default reads, as the builder's placeholder reads.
 */
const DEFAULT_TEXT = 'default';

// %% field

export class RecordedField {
  /**
   * The field's name.
   * @type {string}
   */
  name;

  /**
   * The field's name in words.
   * @type {string}
   */
  label;

  /**
   * Whether the action has no default for the field.
   * @type {boolean}
   */
  required;

  /**
   * The text of the value the action was given, or null when it kept its default.
   * @type {string|null}
   */
  value;

  /**
   * The text of the field's default, or null when the recording names none.
   * @type {string|null}
   */
  default;

  /**
   * What the field's value is, a `FieldValueKind`, or null when the recording does not
   * say.
   * @type {string|null}
   */
  kind;

  /**
   * The pose the action was given in the field, as `[x, y, z, qx, qy, qz, qw]`, or null
   *   when it holds none or the recording does not name it.
   * @type {Array<number>|null}
   */
  pose;

  /**
   * The name of the frame `pose` is given in, or null.
   * @type {string|null}
   */
  frame;

  /**
   * @param {string} name The field's name.
   * @param {boolean} required Whether the action has no default for the field.
   * @param {string|null} value The text of the value the action was given, or null.
   * @param {string|null} defaultValue The text of the field's default, or null.
   * @param {string|null} kind What the field's value is, or null.
   * @param {Object|null} pose The pose the action was given in the field, as the
   *   recording stores it, or null.
   */
  constructor(name, required, value, defaultValue, kind, pose) {
    this.name = name;
    this.label = RecordedStep.fieldWords(name);
    this.required = required;
    this.value = value;
    this.default = defaultValue;
    this.kind = kind;
    this.pose = pose?.[PoseValueKey.POSE] ?? null;
    this.frame = pose?.[PoseValueKey.FRAME] ?? null;
  }

  /**
   * @returns {boolean} Whether the action kept the field's default.
   */
  isDefault() {
    return this.value === null;
  }

  /**
   * @returns {string} The value the action was given, else the default named as the
   *   builder names it.
   */
  text() {
    if (!this.isDefault()) return this.value;
    return this.default === null ? DEFAULT_TEXT : `${DEFAULT_TEXT} (${this.default})`;
  }
}

// %% step

export class RecordedStep {
  /**
   * The step's plan node, as the recording stores it.
   * @type {Object}
   */
  node;

  /**
   * The step's position in its plan, counted from one.
   * @type {number}
   */
  number;

  /**
   * @param {Object} node The step's plan node.
   * @param {number} number Its position in its plan, counted from one.
   */
  constructor(node, number) {
    this.node = node;
    this.number = number;
  }

  /**
   * @param {string} className An action's class name.
   * @returns {string} The words of the name without the `Action` suffix, as the
   *   builder's catalog names actions.
   */
  static words(className) {
    const name = className.endsWith(ACTION_SUFFIX) && className !== ACTION_SUFFIX ? className.slice(0, -ACTION_SUFFIX.length) : className;
    return name.split(WORD_BOUNDARY).join(' ');
  }

  /**
   * @param {string} name The name of an action's field.
   * @returns {string} The name in words, as the builder labels the field.
   */
  static fieldWords(name) {
    return name.split(FIELD_NAME_SEPARATOR).join(' ');
  }

  /**
   * @returns {string} The class name of the step's action.
   */
  get action() {
    return this.node[PlanNodeKey.LABEL];
  }

  /**
   * @returns {string} The step's name in words.
   */
  get label() {
    return RecordedStep.words(this.action);
  }

  /**
   * @returns {string} The step's life-cycle state when the run ended.
   */
  get status() {
    return this.node[PlanNodeKey.STATUS];
  }

  /**
   * @returns {number|null} The first frame the step ran in, or null without frames.
   */
  get start() {
    return this.node[PlanNodeKey.START] ?? null;
  }

  /**
   * @returns {number|null} The last frame the step ran in, or null without frames.
   */
  get end() {
    return this.node[PlanNodeKey.END] ?? null;
  }

  /**
   * @returns {boolean} Whether the recording names the frames the step ran in.
   */
  hasFrames() {
    return this.start !== null && this.end !== null;
  }

  /**
   * @param {number} frame A frame of the replay.
   * @returns {string|null} The step's `StepPhase` at the frame, or null without frames.
   */
  phaseAt(frame) {
    if (!this.hasFrames()) return null;
    if (frame < this.start) return StepPhase.WAITING;
    if (frame > this.end) return StepPhase.DONE;
    return StepPhase.RUNNING;
  }

  /**
   * @returns {Array<{name: string, value: string}>} The fields the step's action was
   *   given, named in words; for a recording that does not name them, the arm and
   *   target the step was recorded with, those it has.
   */
  parameters() {
    const fields = Object.entries(this.node[PlanNodeKey.PARAMETERS] ?? {});
    if (fields.length === 0) return SHOWN_FIELDS.filter((key) => this.node[key]).map((key) => ({ name: key, value: this.node[key] }));
    return fields.map(([name, value]) => ({ name: RecordedStep.fieldWords(name), value }));
  }

  /**
   * @returns {Array<RecordedField>} Every field the step's action declares, in the
   *   order it declares them, with the value it was given; none for a recording that
   *   does not name them.
   */
  fields() {
    const given = this.node[PlanNodeKey.PARAMETERS] ?? {};
    const poses = this.node[PlanNodeKey.POSES] ?? {};
    return (this.node[PlanNodeKey.FIELDS] ?? []).map((field) => {
      const name = field[DeclaredFieldKey.NAME];
      return new RecordedField(name, Boolean(field[DeclaredFieldKey.REQUIRED]), given[name] ?? null, field[DeclaredFieldKey.DEFAULT] ?? null, field[DeclaredFieldKey.KIND] ?? null, poses[name] ?? null);
    });
  }

  /**
   * @returns {Array<Object>} The constraint monitors attached to the step, with what
   *   each observed last.
   */
  constraints() {
    return this.node[PlanNodeKey.CONSTRAINTS] ?? [];
  }
}

// %% plan

export class RecordedPlan {
  /**
   * The plan's root node.
   * @type {Object}
   */
  root;

  /**
   * The plan's position in the recording, counted from one.
   * @type {number}
   */
  number;

  /**
   * The plan's steps, in execution order.
   * @type {Array<RecordedStep>}
   */
  steps;

  /**
   * @param {Object} root A recorded plan's root node.
   * @param {number} number The plan's position in the recording, counted from one.
   */
  constructor(root, number) {
    this.root = root;
    this.number = number;
    this.steps = RecordedPlan.actionsOf(root).map((node, index) => new RecordedStep(node, index + 1));
  }

  /**
   * @returns {string|null} The display name of the robot that performed the plan, or
   *   null when the recording does not name it.
   */
  get robot() {
    return this.root[PlanNodeKey.ROBOT] ?? null;
  }

  /**
   * @returns {string} The robot that performed the plan, else the plan's number.
   */
  title() {
    return this.robot ?? `Plan ${this.number}`;
  }

  /**
   * @param {Object} node A plan node.
   * @returns {Array<Object>} The node when it is an action, else the outermost actions
   *   below it, in execution order.
   */
  static actionsOf(node) {
    if (node[PlanNodeKey.KIND] === PlanNodeKind.ACTION) return [node];
    return (node[PlanNodeKey.CHILDREN] ?? []).flatMap((child) => RecordedPlan.actionsOf(child));
  }

  /**
   * @param {number} frame A frame of the replay.
   * @returns {RecordedStep|null} The step running at the frame, or null between steps.
   */
  stepAt(frame) {
    return this.steps.find((step) => step.phaseAt(frame) === StepPhase.RUNNING) ?? null;
  }
}

// %% plans

export class RecordedPlans {
  /**
   * The plans, one per recorded root.
   * @type {Array<RecordedPlan>}
   */
  plans;

  /**
   * @param {Array<RecordedPlan>} plans The plans.
   */
  constructor(plans) {
    this.plans = plans;
  }

  /**
   * @param {Array<Object>} roots The roots of a recording's plan trees.
   * @returns {RecordedPlans} One plan per root.
   */
  static of(roots) {
    return new RecordedPlans(roots.map((root, index) => new RecordedPlan(root, index + 1)));
  }

  /**
   * @returns {Array<RecordedStep>} The steps of every plan, plan by plan.
   */
  steps() {
    return this.plans.flatMap((plan) => plan.steps);
  }

  /**
   * @returns {boolean} Whether the recording names the frames of any step.
   */
  hasFrames() {
    return this.steps().some((step) => step.hasFrames());
  }
}
