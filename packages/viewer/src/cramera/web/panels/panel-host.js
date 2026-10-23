/**
 * The side panels: one panel shown at a time, most of them with a tab. Panels of
 * plugins the top bar links to have no tab; the top bar shows them. Built-in panels
 * and plugin panels are added the same way.
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
   * @type {Map<string, {panel: SidePanel, tab: HTMLButtonElement|null}>}
   */
  #panels = new Map();

  /**
   * Called with the identity of each panel shown.
   * @type {Array<function(string|null): void>}
   */
  #listeners = [];

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
   * Add a panel; the first panel with a tab is shown.
   * @param {SidePanel} panel The panel.
   * @param {boolean} tabbed Whether the panel has a tab; one without is shown only
   *   when asked for by its identity.
   * @throws {DuplicatePanel} When a panel of the same identity exists.
   */
  add(panel, tabbed = true) {
    if (this.#panels.has(panel.identifier)) throw new DuplicatePanel(panel.identifier);
    const tab = tabbed ? this.#root.ownerDocument.createElement('button') : null;
    if (tab) {
      tab.textContent = panel.title;
      tab.setAttribute('role', 'tab');
      tab.addEventListener('click', () => this.show(panel.identifier));
      this.#tabs.append(tab);
    }
    panel.element.classList.add('panel');
    panel.element.setAttribute('role', 'tabpanel');
    this.#root.append(panel.element);
    this.#panels.set(panel.identifier, { panel, tab });
    this.show(this.#shown ?? (tabbed ? panel.identifier : null));
  }

  /**
   * @param {string} identifier A panel's identity.
   * @returns {boolean} Whether that panel has a tab.
   */
  tabbed(identifier) {
    return Boolean(this.#panels.get(identifier)?.tab);
  }

  /**
   * @returns {UntabbedPanels} The host as a plugin the top bar links to sees it: its
   *   panels are added without a tab.
   */
  withoutTabs() {
    return new UntabbedPanels(this);
  }

  /**
   * @param {string|null} identifier The identity of the panel to show, or null for none.
   */
  show(identifier) {
    this.#shown = identifier;
    for (const [name, { panel, tab }] of this.#panels) {
      panel.element.hidden = name !== identifier;
      tab?.setAttribute('aria-selected', String(name === identifier));
    }
    for (const listener of this.#listeners) listener(identifier);
  }

  /**
   * @param {function(string|null): void} listener Called with the identity of each
   *   panel shown.
   */
  onShow(listener) {
    this.#listeners.push(listener);
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

/**
 * The side panels as a plugin the top bar links to sees them: what it adds has no tab.
 */
export class UntabbedPanels {
  /**
   * The side panels.
   * @type {PanelHost}
   */
  #host;

  /**
   * @param {PanelHost} host The side panels.
   */
  constructor(host) {
    this.#host = host;
  }

  /**
   * @param {SidePanel} panel A panel to add without a tab.
   */
  add(panel) {
    this.#host.add(panel, false);
  }

  /**
   * @param {string} identifier The identity of the panel to show.
   */
  show(identifier) {
    this.#host.show(identifier);
  }

  /**
   * @returns {string|null} The identity of the shown panel.
   */
  get shown() {
    return this.#host.shown;
  }

  /**
   * @returns {Array<string>} The identities of the panels.
   */
  identifiers() {
    return this.#host.identifiers();
  }
}
