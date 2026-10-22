/**
 * The side panels: one tab per panel, one panel shown at a time. Built-in panels and
 * plugin panels are added the same way.
 */

// %% panels

/**
 * One side panel.
 */
export class SidePanel {
  /**
   * @param {string} identifier The panel's identity, unique among the panels.
   * @param {string} title The tab's text.
   * @param {HTMLElement} element The panel's content.
   */
  constructor(identifier, title, element) {
    /**
     * The panel's identity.
     * @type {string}
     */
    this.identifier = identifier;
    /**
     * The tab's text.
     * @type {string}
     */
    this.title = title;
    /**
     * The panel's content.
     * @type {HTMLElement}
     */
    this.element = element;
  }
}

/**
 * A panel added under an identity another panel already has.
 */
export class DuplicatePanel extends Error {
  /**
   * @param {string} identifier The identity both panels use.
   */
  constructor(identifier) {
    super(`A panel named ${identifier} exists already.`);
    /**
     * The identity both panels use.
     * @type {string}
     */
    this.identifier = identifier;
  }
}

export class PanelHost {
  /**
   * The side element.
   * @type {HTMLElement}
   */
  #root;

  /**
   * The tab strip.
   * @type {HTMLElement}
   */
  #tabs;

  /**
   * The panels by identity, in the order they were added.
   * @type {Map<string, {panel: SidePanel, tab: HTMLButtonElement}>}
   */
  #panels = new Map();

  /**
   * The identity of the shown panel.
   * @type {string|null}
   */
  #shown = null;

  /**
   * @param {HTMLElement} root The side element.
   */
  constructor(root) {
    this.#root = root;
    this.#tabs = root.ownerDocument.createElement('div');
    this.#tabs.className = 'tabs';
    this.#tabs.setAttribute('role', 'tablist');
    root.replaceChildren(this.#tabs);
  }

  /**
   * Add a panel; the first panel is shown.
   * @param {SidePanel} panel The panel.
   * @throws {DuplicatePanel} When a panel of the same identity exists.
   */
  add(panel) {
    if (this.#panels.has(panel.identifier)) throw new DuplicatePanel(panel.identifier);
    const tab = this.#root.ownerDocument.createElement('button');
    tab.textContent = panel.title;
    tab.setAttribute('role', 'tab');
    tab.addEventListener('click', () => this.show(panel.identifier));
    panel.element.classList.add('panel');
    panel.element.setAttribute('role', 'tabpanel');
    this.#tabs.append(tab);
    this.#root.append(panel.element);
    this.#panels.set(panel.identifier, { panel, tab });
    this.show(this.#shown ?? panel.identifier);
  }

  /**
   * @param {string} identifier The identity of the panel to show.
   */
  show(identifier) {
    this.#shown = identifier;
    for (const [name, { panel, tab }] of this.#panels) {
      panel.element.hidden = name !== identifier;
      tab.setAttribute('aria-selected', String(name === identifier));
    }
  }

  /**
   * @returns {string|null} The identity of the shown panel.
   */
  get shown() {
    return this.#shown;
  }

  /**
   * @returns {Array<string>} The identities of the panels, in tab order.
   */
  identifiers() {
    return [...this.#panels.keys()];
  }
}
