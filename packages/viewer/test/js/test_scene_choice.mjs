import { test } from 'node:test';
import assert from 'node:assert/strict';

import { SceneChoice, WITHOUT_ENVIRONMENT, WITHOUT_ROBOT } from '../../src/cramera/web/panels/scene-choice.js';
import { IndexEntryKey, IndexKey } from '../../src/cramera/web/protocol.js';

/**
 * @param {string} name Bundle name.
 * @param {string} robot Robot label.
 * @param {string|null} environment Environment label.
 * @param {string|null} task Task label.
 * @returns {Object} An index entry.
 */
function entry(name, robot, environment, task) {
  return { [IndexEntryKey.NAME]: name, [IndexEntryKey.ROBOT]: robot, [IndexEntryKey.ENVIRONMENT]: environment, [IndexEntryKey.TASK]: task };
}

const INDEX = {
  [IndexKey.DEFAULT]: 'pr2_kitchen_pick',
  [IndexKey.SCENES]: [
    entry('pr2_kitchen_pick', 'pr2', 'kitchen', 'pick'),
    entry('pr2_kitchen_pour', 'pr2', 'kitchen', 'pour'),
    entry('pr2_warehouse', 'pr2', 'warehouse', 'transport'),
    entry('tiago_kitchen_pick', 'tiago', 'kitchen', 'pick'),
    entry('warehouse_only', '', 'warehouse', null),
    entry('arm_alone', 'arm', null, null),
  ],
};

test('the default bundle is chosen first', () => {
  const choice = new SceneChoice(INDEX);
  assert.equal(choice.scene, 'pr2_kitchen_pick');
  assert.deepEqual([choice.robot, choice.environment, choice.task], ['pr2', 'kitchen', 'pick']);
});

test('pickers offer only what was recorded with the current choice', () => {
  const choice = new SceneChoice(INDEX);
  assert.deepEqual(choice.robots(), [WITHOUT_ROBOT, 'arm', 'pr2', 'tiago'].sort((a, b) => a.localeCompare(b)));
  assert.deepEqual(choice.environments(), ['kitchen', 'warehouse']);
  assert.deepEqual(choice.tasks(), ['pick', 'pour']);
});

test('changing the robot keeps environment and task when they were recorded', () => {
  const choice = new SceneChoice(INDEX);
  choice.chooseRobot('tiago');
  assert.equal(choice.scene, 'tiago_kitchen_pick');
});

test('changing the robot falls back to its first recording otherwise', () => {
  const choice = new SceneChoice(INDEX);
  choice.chooseTask('pour');
  choice.chooseRobot('tiago');
  assert.equal(choice.scene, 'tiago_kitchen_pick');
});

test('changing the environment and task picks the matching bundle', () => {
  const choice = new SceneChoice(INDEX);
  choice.chooseEnvironment('warehouse');
  assert.equal(choice.scene, 'pr2_warehouse');
  choice.chooseEnvironment('kitchen');
  choice.chooseTask('pour');
  assert.equal(choice.scene, 'pr2_kitchen_pour');
});

test('bundles without robot, environment or task get readable labels', () => {
  const choice = new SceneChoice(INDEX);
  choice.chooseScene('warehouse_only');
  assert.deepEqual([choice.robot, choice.environment, choice.task], [WITHOUT_ROBOT, 'warehouse', 'warehouse_only']);
  choice.chooseScene('arm_alone');
  assert.equal(choice.environment, WITHOUT_ENVIRONMENT);
});

test('choosing an unknown bundle keeps the current one', () => {
  const choice = new SceneChoice(INDEX);
  assert.equal(choice.chooseScene('missing'), false);
  assert.equal(choice.scene, 'pr2_kitchen_pick');
});

test('an index without a default starts with its first bundle, an empty one with none', () => {
  assert.equal(new SceneChoice({ [IndexKey.SCENES]: INDEX[IndexKey.SCENES] }).scene, 'pr2_kitchen_pick');
  const empty = new SceneChoice({});
  assert.equal(empty.scene, null);
  assert.deepEqual(empty.robots(), []);
});
