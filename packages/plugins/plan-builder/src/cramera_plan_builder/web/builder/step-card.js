/**
 * The card of one plan step, as the builder shows it: its number, its action's name and
 * the step's status, on the colour of its action.
 */

/**
 * How many step colours the stylesheet defines; an action takes the colour of its
 * position in the catalog.
 */
export const STEP_PALETTE_SIZE = 8;

/**
 * The classes a step card's elements carry.
 */
export const StepCardClass = Object.freeze({
  STEP: 'step',
  HEAD: 'step-head',
  NUMBER: 'step-number',
  NAME: 'step-name',
  STATUS: 'node-status',
  PARAMETERS: 'step-parameters',
  MORE: 'more-options',
  CHIPS: 'chips',
  CHIP: 'chip',
  BADGE: 'badge',
  OBSERVATION: 'observation',
  DERIVED: 'derived',
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
