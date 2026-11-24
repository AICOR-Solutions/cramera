/**
 * The plan's history of changes, which Undo and Redo travel: each change keeps the
 * whole plan as it was before, as JSON text, and what the change did, as people read it.
 */

import { PlanKey, PlannedObjectKey, PlannedRobotKey, PlanStepKey } from '../../../protocol.js';

/**
 * How many changes the history keeps; an older change can no longer be undone.
 */
export const HISTORY_LIMIT = 100;

/**
 * Which way through the history a key press travels.
 */
export const HistoryTravel = Object.freeze({ UNDO: 'undo', REDO: 'redo' });

/**
 * The shortcuts named in the buttons' tooltips; Cmd stands for Ctrl on macOS.
 */
export const HistoryShortcut = Object.freeze({ UNDO: 'Ctrl+Z', REDO: 'Ctrl+Shift+Z' });

/**
 * The types of input whose text the browser undoes on its own.
 */
const TEXT_INPUT_TYPES = new Set(['text', 'number', 'search', 'url', 'email', 'tel', 'password']);

/**
 * A change in the history: the plan on the other side of it and what it did.
 */
class HistoryEntry {
  /**
   * @param {string} plan The plan before the change when undoing it, after it when
   *   redoing it, as JSON text.
   * @param {string} label What the change did, such as "Move object_1".
   */
  constructor(plan, label) {
    this.plan = plan;
    this.label = label;
  }
}

/**
 * The changes that can be undone and those that can be redone, newest last.
 */
export class PlanHistory {
  /**
   * The changes Undo takes back.
   * @type {Array<HistoryEntry>}
   */
  #undoable = [];

  /**
   * The changes Undo took back, which Redo makes again.
   * @type {Array<HistoryEntry>}
   */
  #redoable = [];

  /**
   * Note a change; what was undone before can no longer be redone.
   * @param {string} before The plan before the change, as JSON text.
   * @param {string} label What the change did.
   */
  record(before, label) {
    this.#undoable.push(new HistoryEntry(before, label));
    if (this.#undoable.length > HISTORY_LIMIT) this.#undoable.shift();
    this.#redoable = [];
  }

  /**
   * @param {string} current The plan as it stands, as JSON text, which Redo comes back to.
   * @returns {string|null} The plan before the latest change, or null without one.
   */
  undo(current) {
    return PlanHistory.#travel(this.#undoable, this.#redoable, current);
  }

  /**
   * @param {string} current The plan as it stands, as JSON text, which Undo comes back to.
   * @returns {string|null} The plan after the change undone last, or null without one.
   */
  redo(current) {
    return PlanHistory.#travel(this.#redoable, this.#undoable, current);
  }

  /**
   * @param {Array<HistoryEntry>} from The changes travelled through.
   * @param {Array<HistoryEntry>} to The changes that travel back.
   * @param {string} current The plan as it stands.
   * @returns {string|null} The plan on the other side of the newest change in `from`.
   */
  static #travel(from, to, current) {
    const entry = from.pop();
    if (entry === undefined) return null;
    to.push(new HistoryEntry(current, entry.label));
    return entry.plan;
  }

  /**
   * @returns {string|null} What Undo takes back, or null when nothing.
   */
  undoLabel() {
    return this.#undoable.at(-1)?.label ?? null;
  }

  /**
   * @returns {string|null} What Redo makes again, or null when nothing.
   */
  redoLabel() {
    return this.#redoable.at(-1)?.label ?? null;
  }

  /**
   * Forget every change, as for another plan.
   */
  clear() {
    this.#undoable = [];
    this.#redoable = [];
  }
}

/**
 * @param {Array<Object>} items Robots, objects or steps.
 * @param {string} key The key of their identity.
 * @returns {Map<string, Object>} The items by their identity.
 */
const byIdentity = (items, key) => new Map((items ?? []).map((item) => [item[key], item]));

/**
 * @param {*} first A part of a plan.
 * @param {*} second Another.
 * @returns {boolean} Whether they differ.
 */
const differ = (first, second) => JSON.stringify(first) !== JSON.stringify(second);

/**
 * @param {Array<Object>} before Items before a change.
 * @param {Array<Object>} after The items after it.
 * @param {string} key The key of their identity.
 * @returns {{added: Array<Object>, removed: Array<Object>, kept: Array<[Object, Object]>}}
 *   The items added, those removed and those kept, before and after.
 */
function compare(before, after, key) {
  const old = byIdentity(before, key);
  const now = byIdentity(after, key);
  return {
    added: [...now.values()].filter((item) => !old.has(item[key])),
    removed: [...old.values()].filter((item) => !now.has(item[key])),
    kept: [...now.values()].filter((item) => old.has(item[key])).map((item) => [old.get(item[key]), item]),
  };
}

/**
 * @param {Object} before A robot before a change.
 * @param {Object} after The robot after it.
 * @param {function(Object): string} stepLabel Names a step.
 * @returns {string|null} What the change did to the robot, or null when nothing.
 */
function describeRobot(before, after, stepLabel) {
  const label = after[PlannedRobotKey.LABEL];
  const steps = compare(before[PlannedRobotKey.STEPS], after[PlannedRobotKey.STEPS], PlanStepKey.IDENTIFIER);
  if (steps.added.length > 0) return `Add step ${stepLabel(steps.added[0])}`;
  if (steps.removed.length > 0) return `Remove step ${stepLabel(steps.removed[0])}`;
  const changed = steps.kept.find(([old, now]) => differ(old, now));
  if (changed) return `Change step ${stepLabel(changed[1])}`;
  if (differ(before[PlannedRobotKey.STEPS], after[PlannedRobotKey.STEPS])) return 'Move a step';
  if (differ(before[PlannedRobotKey.POSE], after[PlannedRobotKey.POSE])) return `Move ${label}`;
  if (differ(before[PlannedRobotKey.JOINT_POSITIONS], after[PlannedRobotKey.JOINT_POSITIONS])) return `Change the posture of ${label}`;
  return differ(before, after) ? `Change ${label}` : null;
}

/**
 * @param {Object} before A plan document before a change.
 * @param {Object} after The plan document after it.
 * @param {function(Object): string} stepLabel Names a step, as its card does.
 * @returns {string} What the change did, as Undo and Redo name it: the first of its
 *   robots, steps, objects and fields that changed.
 */
export function describeChange(before, after, stepLabel) {
  const robots = compare(before[PlanKey.ROBOTS], after[PlanKey.ROBOTS], PlannedRobotKey.IDENTIFIER);
  if (robots.added.length > 0) return `Add robot ${robots.added[0][PlannedRobotKey.LABEL]}`;
  if (robots.removed.length > 0) return `Remove robot ${robots.removed[0][PlannedRobotKey.LABEL]}`;
  for (const [old, now] of robots.kept) {
    const robot = describeRobot(old, now, stepLabel);
    if (robot !== null) return robot;
  }
  const objects = compare(before[PlanKey.OBJECTS], after[PlanKey.OBJECTS], PlannedObjectKey.IDENTIFIER);
  if (objects.added.length + objects.removed.length > 1) return 'Change the objects';
  if (objects.added.length > 0) return `Add ${objects.added[0][PlannedObjectKey.IDENTIFIER]}`;
  if (objects.removed.length > 0) return `Remove ${objects.removed[0][PlannedObjectKey.IDENTIFIER]}`;
  const moved = objects.kept.filter(([old, now]) => differ(old[PlannedObjectKey.POSE], now[PlannedObjectKey.POSE]));
  if (moved.length > 1) return `Move ${moved.length} objects`;
  if (moved.length === 1) return `Move ${moved[0][1][PlannedObjectKey.IDENTIFIER]}`;
  const changed = objects.kept.find(([old, now]) => differ(old, now));
  if (changed) return `Change ${changed[1][PlannedObjectKey.IDENTIFIER]}`;
  if (differ(before[PlanKey.NAME], after[PlanKey.NAME])) return 'Rename the plan';
  if (differ(before[PlanKey.TASK], after[PlanKey.TASK])) return 'Change the task';
  if (differ(before[PlanKey.ENVIRONMENT], after[PlanKey.ENVIRONMENT])) return 'Change the environment';
  const selected = byIdentity(after[PlanKey.ROBOTS], PlannedRobotKey.IDENTIFIER).get(after[PlanKey.SELECTED_ROBOT]);
  if (differ(before[PlanKey.SELECTED_ROBOT], after[PlanKey.SELECTED_ROBOT]) && selected) return `Edit the plan of ${selected[PlannedRobotKey.LABEL]}`;
  return 'Change the plan';
}

/**
 * @param {KeyboardEvent} event A key pressed.
 * @returns {string|null} The `HistoryTravel` the key asks for: Ctrl+Z (Cmd+Z on macOS)
 *   undoes, with Shift, or Ctrl+Y, redoes; null for any other key.
 */
export function historyShortcut(event) {
  if (!(event.ctrlKey || event.metaKey) || event.altKey) return null;
  const key = event.key?.toLowerCase();
  if (key === 'z') return event.shiftKey ? HistoryTravel.REDO : HistoryTravel.UNDO;
  if (key === 'y' && !event.shiftKey) return HistoryTravel.REDO;
  return null;
}

/**
 * @param {Element|null} target What has the keyboard focus.
 * @returns {boolean} Whether it edits text, whose own undo the browser keeps.
 */
export function editsText(target) {
  if (!target) return false;
  if (target.isContentEditable) return true;
  if (target.tagName === 'TEXTAREA') return true;
  return target.tagName === 'INPUT' && TEXT_INPUT_TYPES.has(target.type);
}
