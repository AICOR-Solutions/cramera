/**
 * Constraint rows: each names a variable of the loaded model and the values it may
 * take, symbolic values by checkboxes, numeric ones by an interval. The rows of one
 * list form an event; rows on the same variable are united by the workbench.
 */

import { ConstraintKey, IntervalKey, ModelVariableKey, VariableKind } from '../../protocol.js';

/**
 * The step of the interval inputs of an integer variable.
 */
const INTEGER_STEP = 1;

/**
 * How many steps the interval inputs of a continuous variable divide its range into.
 */
const CONTINUOUS_STEPS = 200;

/**
 * The text of the variable choice before a variable is chosen.
 */
const NO_VARIABLE = 'variable…';

// %% constraint

/**
 * @param {string} variable The variable's name.
 * @param {number} low One end of the interval.
 * @param {number} high The other end.
 * @returns {Object|null} The constraint of a numeric variable lying in the interval, or
 *   null when an end is not a number.
 */
export function intervalConstraint(variable, low, high) {
  if (!Number.isFinite(low) || !Number.isFinite(high)) return null;
  return { [ConstraintKey.VARIABLE]: variable, [ConstraintKey.INTERVALS]: [{ [IntervalKey.LOW]: low, [IntervalKey.HIGH]: high }] };
}

/**
 * @param {string} variable The variable's name.
 * @param {Array<string>} values The values it may take.
 * @returns {Object} The constraint of a symbolic variable taking one of the values.
 */
export function valuesConstraint(variable, values) {
  return { [ConstraintKey.VARIABLE]: variable, [ConstraintKey.VALUES]: values };
}

/**
 * @param {Object} variable A variable of the workbench state.
 * @returns {number} The step of its interval inputs.
 */
export function stepOf(variable) {
  if (variable[ModelVariableKey.KIND] === VariableKind.INTEGER) return INTEGER_STEP;
  return (variable[ModelVariableKey.HIGH] - variable[ModelVariableKey.LOW]) / CONTINUOUS_STEPS;
}

// %% row

export class ConstraintRow {
  /**
   * The row's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * The page.
   * @type {Document}
   */
  #document;

  /**
   * The variable choice.
   * @type {HTMLSelectElement}
   */
  #choice;

  /**
   * The inputs of the chosen variable's values.
   * @type {HTMLElement}
   */
  #inputs;

  /**
   * Reads the row's constraint; null until a variable is chosen.
   * @type {function(): (Object|null)}
   */
  #read = () => null;

  /**
   * @param {Document} document The page.
   * @param {Array<Object>} variables The model's variables, as the workbench state lists them.
   * @param {function(ConstraintRow): void} onRemove Called when the row's remove button is pressed.
   */
  constructor(document, variables, onRemove) {
    this.#document = document;
    this.element = document.createElement('div');
    this.element.className = 'models-row';
    this.#choice = document.createElement('select');
    const empty = document.createElement('option');
    empty.value = '';
    empty.textContent = NO_VARIABLE;
    this.#choice.append(empty);
    for (const variable of variables) {
      const option = document.createElement('option');
      option.value = variable[ModelVariableKey.NAME];
      option.textContent = variable[ModelVariableKey.NAME];
      this.#choice.append(option);
    }
    this.#choice.addEventListener('change', () => this.choose(variables.find((variable) => variable[ModelVariableKey.NAME] === this.#choice.value) ?? null));
    this.#inputs = document.createElement('span');
    this.#inputs.className = 'models-row-values';
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.textContent = '✕';
    remove.title = 'Remove this constraint';
    remove.addEventListener('click', () => onRemove(this));
    this.element.append(this.#choice, this.#inputs, remove);
  }

  /**
   * Show the inputs of a variable's values.
   * @param {Object|null} variable A variable of the workbench state, or null for none.
   */
  choose(variable) {
    this.#choice.value = variable ? variable[ModelVariableKey.NAME] : '';
    this.#inputs.replaceChildren();
    this.#read = () => null;
    if (!variable) return;
    if (variable[ModelVariableKey.KIND] === VariableKind.SYMBOLIC) this.#chooseValues(variable);
    else this.#chooseInterval(variable);
  }

  /**
   * @returns {Object|null} The row's constraint, or null without a variable or with an
   *   interval end that is not a number.
   */
  constraint() {
    return this.#read();
  }

  /**
   * @param {Object} variable A symbolic variable.
   */
  #chooseValues(variable) {
    const boxes = variable[ModelVariableKey.VALUES].map((value) => {
      const label = this.#document.createElement('label');
      const box = this.#document.createElement('input');
      box.type = 'checkbox';
      box.value = value;
      const text = this.#document.createElement('span');
      text.textContent = value;
      label.append(box, text);
      this.#inputs.append(label);
      return box;
    });
    this.#read = () => valuesConstraint(variable[ModelVariableKey.NAME], boxes.filter((box) => box.checked).map((box) => box.value));
  }

  /**
   * @param {Object} variable A numeric variable.
   */
  #chooseInterval(variable) {
    const low = this.#number(variable, variable[ModelVariableKey.LOW]);
    const high = this.#number(variable, variable[ModelVariableKey.HIGH]);
    const between = this.#document.createElement('span');
    between.textContent = ` ≤ ${variable[ModelVariableKey.NAME]} ≤ `;
    this.#inputs.append(low, between, high);
    this.#read = () => intervalConstraint(variable[ModelVariableKey.NAME], Number.parseFloat(low.value), Number.parseFloat(high.value));
  }

  /**
   * @param {Object} variable A numeric variable.
   * @param {number} value The input's first value.
   * @returns {HTMLInputElement} A number input over the variable's range.
   */
  #number(variable, value) {
    const input = this.#document.createElement('input');
    input.type = 'number';
    input.min = String(variable[ModelVariableKey.LOW]);
    input.max = String(variable[ModelVariableKey.HIGH]);
    input.step = String(stepOf(variable));
    input.value = String(value);
    return input;
  }
}

// %% rows

export class ConstraintRows {
  /**
   * The list's element: its heading, its rows and the button adding one.
   * @type {HTMLElement}
   */
  element;

  /**
   * The page.
   * @type {Document}
   */
  #document;

  /**
   * The element holding the rows.
   * @type {HTMLElement}
   */
  #list;

  /**
   * The model's variables.
   * @type {Array<Object>}
   */
  #variables = [];

  /**
   * The rows, in the order they were added.
   * @type {Array<ConstraintRow>}
   */
  rows = [];

  /**
   * @param {Document} document The page.
   * @param {string} title What the rows describe, such as `Evidence`.
   */
  constructor(document, title) {
    this.#document = document;
    this.element = document.createElement('div');
    this.element.className = 'models-rows';
    const heading = document.createElement('h3');
    heading.textContent = title;
    this.#list = document.createElement('div');
    const add = document.createElement('button');
    add.type = 'button';
    add.textContent = '+ Constraint';
    add.addEventListener('click', () => this.add());
    this.element.append(heading, this.#list, add);
  }

  /**
   * Offer another model's variables; the rows are removed.
   * @param {Array<Object>} variables The variables, as the workbench state lists them.
   */
  setVariables(variables) {
    this.#variables = variables;
    this.rows = [];
    this.#list.replaceChildren();
  }

  /**
   * @returns {ConstraintRow|null} A new row, or null without variables to constrain.
   */
  add() {
    if (!this.#variables.length) return null;
    const row = new ConstraintRow(this.#document, this.#variables, (removed) => this.#remove(removed));
    this.rows.push(row);
    this.#list.append(row.element);
    return row;
  }

  /**
   * @returns {Array<Object>} The constraints of the rows that describe one.
   */
  constraints() {
    return this.rows.map((row) => row.constraint()).filter((constraint) => constraint !== null);
  }

  /**
   * @param {ConstraintRow} row A row of the list.
   */
  #remove(row) {
    this.rows = this.rows.filter((candidate) => candidate !== row);
    row.element.remove();
  }
}
