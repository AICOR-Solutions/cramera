/**
 * Building a part's elements and owning its listeners, so the part can remove every
 * listener it added when it is disposed.
 */

/**
 * The names of the builder's controls, kept in `data-action`, so a control can be
 * found by what it does.
 */
export const BuilderAction = Object.freeze({
  NEW: 'new',
  OPEN_SCENE: 'open-scene',
  LOAD_DRAFT: 'load-draft',
  SAVE: 'save',
  SAVE_COPY: 'save-copy',
  EXPORT: 'export',
  IMPORT: 'import',
  UPLOAD: 'upload',
  UNDO: 'undo',
  REDO: 'redo',
  RENAME_DRAFT: 'rename-draft',
  SEARCH: 'search',
  FILTER: 'filter',
  ADD: 'add',
  SELECT: 'select',
  RENAME: 'rename',
  DUPLICATE: 'duplicate',
  REMOVE: 'remove',
  CHOOSE_LINK: 'choose-link',
  RESET_LINK: 'reset-link',
  POSITION: 'position',
  ROTATION: 'rotation',
  SCALE: 'scale',
  PROPORTIONAL: 'proportional',
  JOINT: 'joint',
  VISIBLE: 'visible',
  LOCKED: 'locked',
  OPACITY: 'opacity',
  POINT_SIZE: 'point-size',
  MODE: 'mode',
  FRAME_SELECTION: 'frame-selection',
  FRAME_ALL: 'frame-all',
});

/**
 * The DOM events the builder listens to.
 */
export const DomEvent = Object.freeze({ CLICK: 'click', CHANGE: 'change', INPUT: 'input', KEY_DOWN: 'keydown' });

// %% elements

export class Elements {
  /**
   * The document the elements belong to.
   * @type {Document}
   */
  #document;

  /**
   * Every listener added, to remove them again.
   * @type {Array<[EventTarget, string, function(Event): void]>}
   */
  #listeners = [];

  /**
   * @param {Document} document The document the elements belong to.
   */
  constructor(document) {
    this.#document = document;
  }

  /**
   * @returns {Document} The document the elements belong to.
   */
  get document() {
    return this.#document;
  }

  /**
   * @param {string} tag The element's tag.
   * @param {string=} className Its classes.
   * @param {string=} text Its text, inserted as text, never as HTML.
   * @returns {HTMLElement} The element.
   */
  create(tag, className = '', text = '') {
    const element = this.#document.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  }

  /**
   * @param {string} text The button's text.
   * @param {string} action Its `BuilderAction` value.
   * @param {function(): void} onClick Called on every click.
   * @returns {HTMLButtonElement} The button.
   */
  button(text, action, onClick) {
    const button = this.create('button', '', text);
    button.type = 'button';
    button.dataset.action = action;
    this.listen(button, DomEvent.CLICK, onClick);
    return button;
  }

  /**
   * @param {string} type The input's type.
   * @param {string} action Its `BuilderAction` value.
   * @param {function(): void} onChange Called when the person commits a change.
   * @returns {HTMLInputElement} The input.
   */
  input(type, action, onChange) {
    const input = this.create('input');
    input.type = type;
    input.dataset.action = action;
    this.listen(input, DomEvent.CHANGE, onChange);
    return input;
  }

  /**
   * @param {string} action The select's `BuilderAction` value.
   * @param {function(): void} onChange Called when the person picks an option.
   * @returns {HTMLSelectElement} The select.
   */
  select(action, onChange) {
    const select = this.create('select');
    select.dataset.action = action;
    this.listen(select, DomEvent.CHANGE, onChange);
    return select;
  }

  /**
   * Replace a select's options.
   * @param {HTMLSelectElement} select The select.
   * @param {Array<{value: string, label: string}>} options The options, in order.
   * @param {string} value The value to keep selected, if an option has it.
   */
  options(select, options, value) {
    select.replaceChildren(
      ...options.map((option) => {
        const element = this.create('option', '', option.label);
        element.value = option.value;
        return element;
      }),
    );
    select.value = options.some((option) => option.value === value) ? value : (options[0]?.value ?? '');
  }

  /**
   * @param {string} text The label's text.
   * @param {HTMLElement} control The labelled control.
   * @param {string=} className The label's classes.
   * @returns {HTMLLabelElement} The label holding its text and the control.
   */
  label(text, control, className = '') {
    const label = this.create('label', className);
    label.append(this.create('span', '', text), control);
    return label;
  }

  /**
   * @param {EventTarget} target What to listen on.
   * @param {string} type The event type.
   * @param {function(Event): void} listener The listener.
   */
  listen(target, type, listener) {
    target.addEventListener(type, listener);
    this.#listeners.push([target, type, listener]);
  }

  /**
   * Remove every listener added.
   */
  dispose() {
    for (const [target, type, listener] of this.#listeners) target.removeEventListener(type, listener);
    this.#listeners = [];
  }
}
