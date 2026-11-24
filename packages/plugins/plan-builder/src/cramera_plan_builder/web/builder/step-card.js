/**
 * The card of one plan step, as the builder shows it: its number, its action's name and
 * the step's status, on the colour of its action.
 */

/**
 * How many step colours the stylesheet defines; an action takes the colour
 * `actionPalette` gives it.
 */
export const STEP_PALETTE_SIZE = 8;

/**
 * The colours of the actions most plans use, each one of its own.
 */
const COMMON_ACTION_PALETTE = Object.freeze({
  park_arms: 0,
  navigate: 1,
  pick_up: 2,
  place: 3,
  move_torso: 4,
  transport: 5,
  look_at: 6,
  detect: 7,
});

/**
 * The offset basis and prime of the 32-bit FNV-1a hash the colour of every other
 * action is taken from.
 */
const FNV_OFFSET = 0x811c9dc5;
const FNV_PRIME = 0x01000193;

/**
 * The colour of an action's steps, the same wherever a step of it is shown: in the
 * builder's palette and plan as in a recording's plan view.
 * @param {string} action The action as the builder's catalog identifies it, such as
 *   `park_arms`.
 * @returns {number} The index of its colour among the `STEP_PALETTE_SIZE` the
 *   stylesheet defines: a common action's own, else one taken from the identifier.
 */
export function actionPalette(action) {
  if (Object.hasOwn(COMMON_ACTION_PALETTE, action)) return COMMON_ACTION_PALETTE[action];
  let hash = FNV_OFFSET;
  for (const character of action) hash = Math.imul(hash ^ character.codePointAt(0), FNV_PRIME) >>> 0;
  return hash % STEP_PALETTE_SIZE;
}

/**
 * The classes a step card's elements carry.
 */
export const StepCardClass = Object.freeze({
  STEP: 'step',
  HEAD: 'step-head',
  NUMBER: 'step-number',
  NAME: 'step-name',
  STATUS: 'node-status',
});

// %% card

export class StepCard {
  /**
   * The card.
   * @type {HTMLLIElement}
   */
  card;

  /**
   * The card's head line: number, name, status and whatever the owner appends.
   * @type {HTMLElement}
   */
  head;

  /**
   * Builds the card's elements.
   * @type {import('./elements.js').Elements}
   */
  #elements;

  /**
   * The status chip, once a status was shown.
   * @type {HTMLElement|null}
   */
  #status = null;

  /**
   * @param {import('./elements.js').Elements} elements Builds the card's elements.
   * @param {number} number The step's position in its plan, counted from one.
   * @param {string} name The name of the step's action.
   * @param {string} description What the name stands for, shown as its tooltip.
   * @param {number} palette The colour of the step's action.
   */
  constructor(elements, number, name, description, palette) {
    this.#elements = elements;
    this.card = elements.create('li', StepCardClass.STEP);
    this.card.dataset.palette = String(palette);
    this.head = elements.create('div', StepCardClass.HEAD);
    const label = elements.create('span', StepCardClass.NAME, name);
    label.title = description;
    this.head.append(elements.create('span', StepCardClass.NUMBER, String(number)), label);
    this.card.append(this.head);
  }

  /**
   * Show the step's status in the head, after its name.
   * @param {string} status The status.
   */
  showStatus(status) {
    if (this.#status === null) {
      this.#status = this.#elements.create('span', StepCardClass.STATUS);
      this.head.append(this.#status);
    }
    this.#status.textContent = status;
    this.#status.dataset.status = status;
  }
}
