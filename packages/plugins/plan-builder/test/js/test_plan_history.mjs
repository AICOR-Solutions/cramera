import { test } from 'node:test';
import assert from 'node:assert/strict';

import { PlanKey, PlannedObjectKey, PlannedRobotKey, PlanStepKey } from 'cramera-viewer/protocol.js';
import { HISTORY_LIMIT, HistoryTravel, PlanHistory, describeChange, editsText, historyShortcut } from '../../src/cramera_plan_builder/web/builder/plan-history.js';

const stepLabel = (step) => step[PlanStepKey.ACTION];

/**
 * @param {Array<Object>} steps The robot's steps.
 * @param {Object<string, *>} changes What else differs from the plain robot.
 * @returns {Object} A plan document of one robot and one object.
 */
const plan = (steps = [], changes = {}) => ({
  [PlanKey.NAME]: 'stack',
  [PlanKey.ROBOTS]: [{ [PlannedRobotKey.IDENTIFIER]: 'robot_1', [PlannedRobotKey.LABEL]: 'Tracy', [PlannedRobotKey.POSE]: [0, 0, 0, 0, 0, 0, 1], [PlannedRobotKey.STEPS]: steps, ...changes.robot }],
  [PlanKey.OBJECTS]: changes.objects ?? [{ [PlannedObjectKey.IDENTIFIER]: 'object_1', [PlannedObjectKey.POSE]: [1, 0, 0.8, 0, 0, 0, 1] }],
});
const step = (identifier, action, values = {}) => ({ [PlanStepKey.IDENTIFIER]: identifier, [PlanStepKey.ACTION]: action, [PlanStepKey.VALUES]: values });

test('an undone change is redone, and a new change drops what was undone', () => {
  const history = new PlanHistory();
  history.record('a', 'Add step');
  history.record('b', 'Rename the plan');
  assert.equal(history.undoLabel(), 'Rename the plan');
  assert.equal(history.undo('c'), 'b');
  assert.equal(history.redoLabel(), 'Rename the plan');
  assert.equal(history.undo('b'), 'a');
  assert.equal(history.undoLabel(), null);
  assert.equal(history.undo('a'), null);
  assert.equal(history.redo('a'), 'b');
  assert.equal(history.undoLabel(), 'Add step');
  history.record('b', 'Move object_1');
  assert.equal(history.redoLabel(), null);
  assert.equal(history.redo('d'), null);
});

test('the history keeps the latest changes only, up to its limit', () => {
  const history = new PlanHistory();
  for (let index = 0; index <= HISTORY_LIMIT; index++) history.record(String(index), `change ${index}`);
  let undone = 0;
  let plan = 'now';
  for (let previous = history.undo(plan); previous !== null; previous = history.undo(plan)) {
    plan = previous;
    undone += 1;
  }
  assert.equal(undone, HISTORY_LIMIT);
  assert.equal(plan, '1');
});

test('a cleared history has nothing to undo or redo', () => {
  const history = new PlanHistory();
  history.record('a', 'Add step');
  history.undo('b');
  history.record('b', 'Add step');
  history.clear();
  assert.deepEqual([history.undoLabel(), history.redoLabel()], [null, null]);
});

test('a change is named by what it did to the plan', () => {
  const picked = [step('step_1', 'pick_up')];
  const name = (before, after) => describeChange(before, after, stepLabel);
  assert.equal(name(plan(), plan(picked)), 'Add step pick_up');
  assert.equal(name(plan(picked), plan()), 'Remove step pick_up');
  assert.equal(name(plan([...picked, step('step_2', 'place')]), plan([step('step_2', 'place'), ...picked])), 'Move a step');
  assert.equal(name(plan(picked), plan([step('step_1', 'pick_up', { arm: 'left' })])), 'Change step pick_up');
  assert.equal(name(plan(), plan([], { robot: { [PlannedRobotKey.POSE]: [1, 0, 0, 0, 0, 0, 1] } })), 'Move Tracy');
  assert.equal(name(plan(), plan([], { robot: { [PlannedRobotKey.LABEL]: 'Tracy 2' } })), 'Change Tracy 2');
  assert.equal(name(plan(), plan([], { objects: [{ [PlannedObjectKey.IDENTIFIER]: 'object_1', [PlannedObjectKey.POSE]: [2, 0, 0.8, 0, 0, 0, 1] }] })), 'Move object_1');
  assert.equal(name(plan(), plan([], { objects: [] })), 'Remove object_1');
  assert.equal(name(plan(), { ...plan(), [PlanKey.NAME]: 'tower' }), 'Rename the plan');
  assert.equal(name(plan(), { ...plan(), [PlanKey.ENVIRONMENT]: 'kitchen' }), 'Change the environment');
  assert.equal(name(plan(), { ...plan(), [PlanKey.ROBOTS]: [] }), 'Remove robot Tracy');
});

test('Ctrl or Cmd with Z undoes, with Shift or Y redoes, and other keys travel nowhere', () => {
  assert.equal(historyShortcut({ key: 'z', ctrlKey: true }), HistoryTravel.UNDO);
  assert.equal(historyShortcut({ key: 'z', metaKey: true }), HistoryTravel.UNDO);
  assert.equal(historyShortcut({ key: 'Z', ctrlKey: true, shiftKey: true }), HistoryTravel.REDO);
  assert.equal(historyShortcut({ key: 'y', ctrlKey: true }), HistoryTravel.REDO);
  assert.equal(historyShortcut({ key: 'z' }), null);
  assert.equal(historyShortcut({ key: 'z', ctrlKey: true, altKey: true }), null);
  assert.equal(historyShortcut({ key: 's', ctrlKey: true }), null);
});

test('text fields keep their own undo, other controls do not', () => {
  const input = (type) => ({ tagName: 'INPUT', type });
  assert.equal(editsText(input('text')), true);
  assert.equal(editsText(input('number')), true);
  assert.equal(editsText({ tagName: 'TEXTAREA' }), true);
  assert.equal(editsText({ tagName: 'DIV', isContentEditable: true }), true);
  assert.equal(editsText(input('checkbox')), false);
  assert.equal(editsText({ tagName: 'BUTTON' }), false);
  assert.equal(editsText(null), false);
});
