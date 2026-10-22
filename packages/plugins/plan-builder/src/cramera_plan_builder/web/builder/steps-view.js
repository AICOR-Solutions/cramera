/**
 * The edited robot's plan: the palette of the actions its model offers, and the steps
 * with their parameters, constraints and live state; actions are dragged or clicked into
 * the plan, constraints dragged onto a step.
 */

import {
  PlacementMode,
  PlanBuilderCatalogKey,
  PlannedObjectKey,
  PlanStepKey,
  StepConstraintKey,
  StepKind,
} from '../../../protocol.js';
import { DragKind, DragText, Elements, PlanAction } from './elements.js';
import { OBJECT_STEPS, PUTTING_DOWN } from './plan-state.js';
import { PlanPose } from './poses.js';

/**
 * How people read each step kind.
 */
export const STEP_LABELS = Object.freeze({
  [StepKind.PARK_ARMS]: 'Park arms',
  [StepKind.MOVE_TORSO]: 'Move torso',
  [StepKind.NAVIGATE]: 'Navigate',
  [StepKind.TRANSPORT]: 'Transport object',
  [StepKind.PICK_UP]: 'Pick up',
  [StepKind.PLACE]: 'Place',
});

/**
 * How people read each way of putting an object down.
 */
const PLACEMENT_LABELS = Object.freeze({
  [PlacementMode.POSE]: 'at a pose',
  [PlacementMode.SURFACE]: 'on a surface',
});

/**
 * The surface choice that lets the step take any surface of its type.
 */
const ANY_SURFACE = Object.freeze({ value: '', label: 'any of the type' });

/**
 * The classes the view's elements carry.
 */
const ViewClass = Object.freeze({
  PALETTE: 'palette',
  BLOCK: 'block',
  LIST: 'steps',
  STEP: 'step',
  STEP_HEAD: 'step-head',
  PARAMETERS: 'step-parameters',
  CHIPS: 'chips',
  CHIP: 'chip',
  DROP: 'drop-hint',
  DRAG_OVER: 'drag-over',
  STATUS: 'node-status',
  EMPTY: 'empty',
});

// %% view

export class StepsView {
  /**
   * The palette of actions.
   * @type {HTMLElement}
   */
  palette;

  /**
   * The list of steps.
   * @type {HTMLElement}
   */
  list;

  /**
   * The page that applies the person's edits.
   * @type {Object}
   */
  #editor;

  /**
   * Owns the listeners of the list's frame.
   * @type {Elements}
   */
  #frame;

  /**
   * Owns the listeners of the shown palette and steps, replaced on every render.
   * @type {Elements}
   */
  #shown;

  /**
   * @param {Document} document The page's document.
   * @param {Object} editor The page: `state` (the `PlanState`), `edit(change)` (applies
   *   a change of the plan and shows it), `attachConstraint(stepIdentifier, text)`,
   *   `useLivePose(stepIdentifier)` and `surfaces()` (the live world's surface names
   *   by type).
   */
  constructor(document, editor) {
    this.#editor = editor;
    this.#frame = new Elements(document);
    this.#shown = new Elements(document);
    this.palette = this.#frame.create('div', ViewClass.PALETTE);
    this.list = this.#frame.create('ol', ViewClass.LIST);
    this.#frame.dropTarget(this.list, ViewClass.DRAG_OVER, (text) => this.#dropped(text, this.#editor.state.steps().length));
  }

  /**
   * Show the edited robot's palette and steps.
   * @param {Array<string|null>} statuses The live status of each step, by position.
   * @param {Array<Map<string, string|null>>} observations What each step's constraints
   *   observe in the live plan, by their text, by position.
   */
  render(statuses = [], observations = []) {
    this.#shown.dispose();
    this.#shown = new Elements(this.#frame.document);
    const state = this.#editor.state;
    const robot = state.activeRobot();
    const offered = robot ? state.offeredSteps(robot) : [];
    this.palette.replaceChildren(
      ...offered.map((kind) => {
        const block = this.#shown.button(STEP_LABELS[kind], PlanAction.ADD_STEP, () => this.#add(kind, state.steps().length));
        block.className = `${ViewClass.BLOCK} ${kind}`;
        block.dataset.kind = kind;
        this.#shown.draggable(block, DragText.of(DragKind.STEP, kind));
        return block;
      }),
    );
    const steps = state.steps();
    if (steps.length === 0) {
      this.list.replaceChildren(this.#shown.create('li', ViewClass.DROP, 'Drag actions here, or click them, to build the plan.'));
      return;
    }
    this.list.replaceChildren(...steps.map((step, index) => this.#card(step, index, statuses[index] ?? null, observations[index] ?? new Map())));
  }

  /**
   * @param {Object} step A step of the edited robot.
   * @param {number} index Its position.
   * @param {string|null} status Its live status, or null.
   * @param {Map<string, string|null>} observations What its constraints observe live.
   * @returns {HTMLElement} The step's card.
   */
  #card(step, index, status, observations) {
    const elements = this.#shown;
    const identifier = step[PlanStepKey.IDENTIFIER];
    const kind = step[PlanStepKey.KIND];
    const card = elements.create('li', `${ViewClass.STEP} ${kind}`);
    card.dataset.step = identifier;
    const head = elements.create('div', ViewClass.STEP_HEAD);
    head.append(
      elements.create('span', 'step-number', String(index + 1)),
      elements.create('span', 'step-name', STEP_LABELS[kind]),
    );
    if (status) {
      const chip = elements.create('span', ViewClass.STATUS, status);
      chip.dataset.status = status;
      head.append(chip);
    }
    const controls = elements.create('span', 'step-controls');
    controls.append(
      elements.button('↑', PlanAction.MOVE_STEP_UP, () => this.#edit(() => this.#editor.state.moveStep(identifier, -1))),
      elements.button('↓', PlanAction.MOVE_STEP_DOWN, () => this.#edit(() => this.#editor.state.moveStep(identifier, 1))),
      elements.button('×', PlanAction.REMOVE_STEP, () => this.#edit(() => this.#editor.state.removeStep(identifier))),
    );
    head.append(controls);
    card.append(head, this.#parameters(step), this.#chips(step, observations));
    elements.dropTarget(card, ViewClass.DRAG_OVER, (text) => this.#dropped(text, index, identifier));
    return card;
  }

  /**
   * @param {Object} step A step of the edited robot.
   * @returns {HTMLElement} The controls of the step's parameters.
   */
  #parameters(step) {
    const elements = this.#shown;
    const state = this.#editor.state;
    const identifier = step[PlanStepKey.IDENTIFIER];
    const kind = step[PlanStepKey.KIND];
    const update = (changes) => this.#edit(() => state.updateStep(identifier, changes));
    const box = elements.create('div', ViewClass.PARAMETERS);
    const choices = (values) => values.map((value) => ({ value, label: value }));
    if (OBJECT_STEPS.includes(kind)) {
      const objects = state.objects().map((item) => ({ value: item[PlannedObjectKey.IDENTIFIER], label: item[PlannedObjectKey.IDENTIFIER] }));
      if (objects.length === 0) box.append(elements.create('p', ViewClass.EMPTY, 'Add an object for this step to act on.'));
      else box.append(elements.label('object', elements.select(PlanAction.STEP_PARAMETER, objects, step[PlanStepKey.OBJECT], (value) => update({ [PlanStepKey.OBJECT]: value }))));
    }
    if (step[PlanStepKey.ARM] !== undefined) {
      box.append(elements.label('arm', elements.select(PlanAction.STEP_PARAMETER, choices(state.offeredArms(state.activeRobot())), step[PlanStepKey.ARM], (value) => update({ [PlanStepKey.ARM]: value }))));
    }
    if (kind === StepKind.MOVE_TORSO) {
      box.append(elements.label('height', elements.select(PlanAction.STEP_PARAMETER, choices(state.catalog[PlanBuilderCatalogKey.TORSO_STATES]), step[PlanStepKey.TORSO_STATE], (value) => update({ [PlanStepKey.TORSO_STATE]: value }))));
    }
    if (PUTTING_DOWN.includes(kind)) box.append(...this.#destination(step, update));
    if (kind === StepKind.NAVIGATE) {
      box.append(...this.#pose(step, update));
      const capture = elements.button('Use the robot’s live pose', PlanAction.USE_LIVE_POSE, () => this.#editor.useLivePose(identifier));
      box.append(capture);
    }
    return box;
  }

  /**
   * @param {Object} step A step that puts an object down.
   * @param {function(Object): void} update Applies parameter changes.
   * @returns {Array<HTMLElement>} The choice of pose or surface and its controls.
   */
  #destination(step, update) {
    const elements = this.#shown;
    const placement = step[PlanStepKey.PLACEMENT] ?? PlacementMode.POSE;
    const modes = Object.values(PlacementMode).map((mode) => ({ value: mode, label: PLACEMENT_LABELS[mode] }));
    const controls = [elements.label('put down', elements.select(PlanAction.STEP_PARAMETER, modes, placement, (value) => update({ [PlanStepKey.PLACEMENT]: value })))];
    if (placement === PlacementMode.POSE) return [...controls, ...this.#pose(step, update)];
    const types = this.#editor.state.catalog[PlanBuilderCatalogKey.SURFACE_TYPES].map((type) => ({ value: type, label: type }));
    const surfaceType = step[PlanStepKey.SURFACE_TYPE];
    const named = (this.#editor.surfaces().get(surfaceType) ?? []).map((name) => ({ value: name, label: name }));
    controls.push(
      elements.label('surface', elements.select(PlanAction.STEP_PARAMETER, types, surfaceType, (value) => update({ [PlanStepKey.SURFACE_TYPE]: value, [PlanStepKey.SURFACE_NAME]: null }))),
      elements.label('which', elements.select(PlanAction.STEP_PARAMETER, [ANY_SURFACE, ...named], step[PlanStepKey.SURFACE_NAME] ?? ANY_SURFACE.value, (value) => update({ [PlanStepKey.SURFACE_NAME]: value || null }))),
    );
    return controls;
  }

  /**
   * @param {Object} step A step with a target pose.
   * @param {function(Object): void} update Applies parameter changes.
   * @returns {Array<HTMLElement>} The controls of the target's position and heading.
   */
  #pose(step, update) {
    const elements = this.#shown;
    const target = step[PlanStepKey.TARGET] ?? PlanPose.of(0, 0, 0, 0);
    const position = PlanPose.position(target);
    const row = elements.create('div', 'pose-row');
    const coordinates = ['x', 'y', 'z'].map((axis, index) =>
      elements.number(axis, position[index], PlanAction.POSE, (value) => {
        const moved = [...position];
        moved[index] = value;
        update({ [PlanStepKey.TARGET]: PlanPose.moved(target, moved) });
      }),
    );
    const heading = elements.number('yaw°', PlanPose.degrees(PlanPose.yaw(target)), PlanAction.POSE, (value) => update({ [PlanStepKey.TARGET]: PlanPose.turned(target, PlanPose.radians(value)) }));
    row.append(...coordinates, heading);
    return [row];
  }

  /**
   * @param {Object} step A step of the edited robot.
   * @param {Map<string, string|null>} observations What its constraints observe live.
   * @returns {HTMLElement} The step's constraints, each removable, with what the live
   *   publisher observes.
   */
  #chips(step, observations) {
    const elements = this.#shown;
    const identifier = step[PlanStepKey.IDENTIFIER];
    const chips = elements.create('div', ViewClass.CHIPS);
    (step[PlanStepKey.CONSTRAINTS] ?? []).forEach((constraint, index) => {
      const chip = elements.create('span', ViewClass.CHIP);
      const monitor = constraint[StepConstraintKey.MONITOR_TYPE] ?? '';
      chip.title = constraint[StepConstraintKey.SWITCH] ?? monitor;
      chip.append(elements.create('span', '', constraint[StepConstraintKey.TEXT]));
      if (monitor) chip.append(elements.create('span', 'badge', monitor));
      const observed = observations.get(constraint[StepConstraintKey.TEXT]);
      if (observed) {
        const badge = elements.create('span', 'observation', observed);
        badge.dataset.observation = observed;
        chip.append(badge);
      }
      chip.append(elements.button('×', PlanAction.DETACH_CONSTRAINT, () => this.#edit(() => this.#editor.state.detachConstraint(identifier, index))));
      chips.append(chip);
    });
    return chips;
  }

  /**
   * @param {string} text A drag's text.
   * @param {number} index Where a dropped action goes.
   * @param {string=} identifier The step a constraint was dropped on.
   */
  #dropped(text, index, identifier) {
    const kind = DragText.valueOf(text, DragKind.STEP);
    if (kind !== null) {
      this.#add(kind, index);
      return;
    }
    const sentence = DragText.valueOf(text, DragKind.CONSTRAINT);
    if (sentence !== null && identifier !== undefined) this.#editor.attachConstraint(identifier, sentence);
  }

  /**
   * @param {string} kind A `StepKind` value.
   * @param {number} index Where the step goes.
   */
  #add(kind, index) {
    this.#edit(() => this.#editor.state.addStep(kind, index));
  }

  /**
   * @param {function(): void} change A change of the plan.
   */
  #edit(change) {
    this.#editor.edit(change);
  }

  /**
   * Remove every listener.
   */
  dispose() {
    this.#shown.dispose();
    this.#frame.dispose();
  }
}
