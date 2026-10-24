/**
 * The plans a recording performed, as steps: each plan's outermost actions, with the
 * frames each ran in, so the step at any frame of the replay is known.
 */

import { PlanNodeKey, PlanNodeKind } from '../../../protocol.js';
import { planNodeKindOf } from '../../../core/plan-node-kinds.js';

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
 * The recorded fields a step's card shows, in order, when the recording was written
 * before plan nodes carried every parameter.
 */
const SHOWN_FIELDS = Object.freeze([PlanNodeKey.ARM, PlanNodeKey.TARGET]);

/**
 * Separates the words of a parameter's name, which its label replaces with spaces.
 */
const NAME_SEPARATOR = '_';

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
   * @param {string} name A parameter's name, as the action declares it.
   * @returns {string} The name in words, as the builder labels the field.
   */
  static fieldLabel(name) {
    return name.split(NAME_SEPARATOR).join(' ');
  }

  /**
   * @returns {Array<{name: string, value: string}>} Every parameter the step was
   *   recorded with, labelled as the builder labels the field; for a recording
   *   written before plan nodes carried them, the arm and target it has.
   */
  parameters() {
    const recorded = Object.entries(this.node[PlanNodeKey.PARAMETERS] ?? {});
    if (recorded.length > 0) return recorded.map(([name, value]) => ({ name: RecordedStep.fieldLabel(name), value }));
    return SHOWN_FIELDS.filter((key) => this.node[key]).map((key) => ({ name: key, value: this.node[key] }));
  }

  /**
   * @returns {Array<Object>} The constraints attached to the step while it ran, as
   *   the recording stores them.
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
    if (planNodeKindOf(node[PlanNodeKey.KIND]) === PlanNodeKind.ACTION) return [node];
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
