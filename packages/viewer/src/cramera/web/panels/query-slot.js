/**
 * The slot above the side panels that one plugin may fill with its question panel,
 * shown as a card with a heading; empty, the slot is hidden and the side panels take
 * the whole column.
 */

// %% slot

/**
 * What a plugin puts into the query slot.
 */
export class SlotPanel {
  /**
   * @param {string} identifier The identity of the plugin filling the slot.
   * @param {string} title The card's heading.
   * @param {HTMLElement} element The card's content.
   * @param {HTMLElement|null} aside What the card's head shows next to the heading, or
   *   null for nothing.
   */
  constructor(identifier, title, element, aside = null) {
    /**
     * The identity of the plugin filling the slot.
     * @type {string}
     */
    this.identifier = identifier;
    /**
     * The card's heading.
     * @type {string}
     */
    this.title = title;
    /**
     * The card's content.
     * @type {HTMLElement}
     */
    this.element = element;
    /**
     * What the card's head shows next to the heading.
     * @type {HTMLElement|null}
     */
    this.aside = aside;
  }
}

/**
 * A second plugin asking for a slot another plugin fills.
 */
export class SlotTaken extends Error {
  /**
   * @param {string} occupant The identity of the plugin filling the slot.
   * @param {string} identifier The identity of the plugin asking.
   */
  constructor(occupant, identifier) {
    super(`The query slot is filled by ${occupant}; ${identifier} cannot fill it too.`);
    /**
     * The identity of the plugin filling the slot.
     * @type {string}
     */
    this.occupant = occupant;
    /**
     * The identity of the plugin asking.
     * @type {string}
     */
    this.identifier = identifier;
  }
}

export class QuerySlot {
  /**
   * The slot's card.
   * @type {HTMLElement}
   */
  #root;

  /**
   * The panel filling the slot, or null.
   * @type {SlotPanel|null}
   */
  #panel = null;

  /**
   * @param {HTMLElement} root The slot's card; hidden while the slot is empty.
   */
  constructor(root) {
    this.#root = root;
    root.hidden = true;
  }

  /**
   * Fill the slot.
   * @param {SlotPanel} panel What the slot shows.
   * @throws {SlotTaken} When another plugin fills the slot.
   */
  fill(panel) {
    if (this.#panel) throw new SlotTaken(this.#panel.identifier, panel.identifier);
    const document = this.#root.ownerDocument;
    const head = document.createElement('div');
    head.className = 'card-head';
    const heading = document.createElement('h2');
    heading.textContent = panel.title;
    head.append(heading);
    if (panel.aside) head.append(panel.aside);
    panel.element.classList.add('slot-body');
    this.#root.replaceChildren(head, panel.element);
    this.#root.hidden = false;
    this.#panel = panel;
  }

  /**
   * @returns {string|null} The identity of the plugin filling the slot, or null.
   */
  get occupant() {
    return this.#panel?.identifier ?? null;
  }
}
