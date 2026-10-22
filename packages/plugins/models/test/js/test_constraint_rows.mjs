import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { ConstraintKey, IntervalKey, ModelVariableKey, VariableKind, WorkbenchStateKey } from 'cramera-viewer/protocol.js';
import { ConstraintRows, intervalConstraint, stepOf, valuesConstraint } from '../../src/cramera_models/web/constraint-rows.js';
import { FakeDocument } from 'cramera-testing/fake-document.mjs';

/**
 * The variables of the tests: a symbolic, a continuous and an integer one.
 */
const VARIABLES = JSON.parse(readFileSync(new URL('./workbench_state.json', import.meta.url), 'utf-8'))[WorkbenchStateKey.VARIABLES];

/**
 * @param {string} kind A `VariableKind` value.
 * @returns {Object} The test variable of that kind.
 */
function variableOf(kind) {
  return VARIABLES.find((variable) => variable[ModelVariableKey.KIND] === kind);
}

/**
 * @param {Object} row A constraint row.
 * @returns {Array<Object>} The row's inputs.
 */
function inputsOf(row) {
  return row.element.findAll((element) => element.tagName === 'INPUT');
}

// %% constraints

test('an interval constraint names the variable and both ends', () => {
  assert.deepEqual(intervalConstraint('x', 0.5, 0.25), {
    [ConstraintKey.VARIABLE]: 'x',
    [ConstraintKey.INTERVALS]: [{ [IntervalKey.LOW]: 0.5, [IntervalKey.HIGH]: 0.25 }],
  });
  assert.equal(intervalConstraint('x', Number.NaN, 1), null);
});

test('a values constraint names the variable and the values', () => {
  assert.deepEqual(valuesConstraint('color', ['red']), { [ConstraintKey.VARIABLE]: 'color', [ConstraintKey.VALUES]: ['red'] });
});

test('integer inputs step by one, continuous ones by a fraction of the range', () => {
  assert.equal(stepOf(variableOf(VariableKind.INTEGER)), 1);
  const continuous = variableOf(VariableKind.CONTINUOUS);
  assert.ok(stepOf(continuous) > 0 && stepOf(continuous) < continuous[ModelVariableKey.HIGH] - continuous[ModelVariableKey.LOW]);
});

// %% rows

test('a row without a chosen variable describes no constraint', () => {
  const rows = new ConstraintRows(new FakeDocument(), 'Evidence');
  rows.setVariables(VARIABLES);
  rows.add();
  assert.deepEqual(rows.constraints(), []);
});

test('a symbolic row describes the checked values', () => {
  const rows = new ConstraintRows(new FakeDocument(), 'Evidence');
  rows.setVariables(VARIABLES);
  const row = rows.add();
  const symbolic = variableOf(VariableKind.SYMBOLIC);
  row.choose(symbolic);
  const boxes = inputsOf(row);
  assert.equal(boxes.length, symbolic[ModelVariableKey.VALUES].length);
  boxes[1].checked = true;
  assert.deepEqual(rows.constraints(), [valuesConstraint(symbolic[ModelVariableKey.NAME], [symbolic[ModelVariableKey.VALUES][1]])]);
});

test('a numeric row starts with the whole range and reads the typed ends', () => {
  const rows = new ConstraintRows(new FakeDocument(), 'Query');
  rows.setVariables(VARIABLES);
  const row = rows.add();
  const numeric = variableOf(VariableKind.CONTINUOUS);
  row.choose(numeric);
  const name = numeric[ModelVariableKey.NAME];
  assert.deepEqual(rows.constraints(), [intervalConstraint(name, numeric[ModelVariableKey.LOW], numeric[ModelVariableKey.HIGH])]);
  inputsOf(row)[1].value = '0.5';
  assert.deepEqual(rows.constraints(), [intervalConstraint(name, numeric[ModelVariableKey.LOW], 0.5)]);
});

test('the variable choice shows the inputs of the chosen variable', () => {
  const rows = new ConstraintRows(new FakeDocument(), 'Query');
  rows.setVariables(VARIABLES);
  const row = rows.add();
  const choice = row.element.findAll((element) => element.tagName === 'SELECT')[0];
  choice.value = variableOf(VariableKind.INTEGER)[ModelVariableKey.NAME];
  choice.dispatch('change');
  assert.equal(inputsOf(row).length, 2);
  choice.value = '';
  choice.dispatch('change');
  assert.equal(inputsOf(row).length, 0);
});

test('a removed row no longer counts and new variables clear the rows', () => {
  const rows = new ConstraintRows(new FakeDocument(), 'Query');
  assert.equal(rows.add(), null);
  rows.setVariables(VARIABLES);
  const kept = rows.add();
  const removed = rows.add();
  removed.element.findAll((element) => element.tagName === 'BUTTON')[0].dispatch('click');
  assert.deepEqual(rows.rows, [kept]);
  rows.setVariables([]);
  assert.deepEqual(rows.rows, []);
});
