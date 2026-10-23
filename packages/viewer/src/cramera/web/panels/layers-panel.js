/**
 * The Layers overlay in the corner of the 3D view: switches for what the view draws
 * and the list of the scene's free objects, which light up when picked. It folds down
 * to its title.
 */

// %% switches

/**
 * One switch of the overlay.
 */
export class ViewSwitch {
  /**
   * @param {string} label What the switch changes.
   * @param {function(): boolean} read Whether it is on now.
   * @param {function(boolean): void} write Turns it on or off.
   */
  constructor(label, read, write) {
    /**
     * What the switch changes.
     * @type {string}
     */
    this.label = label;
    /**
     * Whether it is on now.
     * @type {function(): boolean}
     */
    this.read = read;
    /**
     * Turns it on or off.
     * @type {function(boolean): void}
     */
    this.write = write;
  }
}

/**
 * One free object of the scene in the overlay's list.
 */
export class LayerObject {
  /**
   * @param {string} key The object's key, under which answers light it up.
   * @param {string} label The object's name as the list shows it.
   */
  constructor(key, label) {
    /**
     * The object's key.
     * @type {string}
     */
    this.key = key;
    /**
     * The object's name as the list shows it.
     * @type {string}
     */
    this.label = label;
  }
}

// %% overlay

export class LayersPanel {
  /**
   * The overlay's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * The switches with their checkboxes.
   * @type {Array<{viewSwitch: ViewSwitch, input: HTMLInputElement}>}
   */
  #switches = [];

  /**
   * The list of free objects.
   * @type {HTMLElement}
   */
  #objects;

  /**
   * The fold button.
   * @type {HTMLButtonElement}
   */
  #fold;

  /**
   * Called with the key of an object picked from the list.
   * @type {function(string): void}
   */
  #onPick;

  /**
   * @param {HTMLElement} element The overlay's element.
   * @param {Array<ViewSwitch>} switches The switches to offer.
   * @param {function(string): void} onPick Called with the key of an object picked
   *   from the list.
   */
  constructor(element, switches, onPick) {
    const document = element.ownerDocument;
    this.element = element;
    this.#onPick = onPick;
    const title = document.createElement('p');
    title.className = 'layers-title';
    const caption = document.createElement('span');
    caption.textContent = 'Layers';
    const fold = document.createElement('button');
    fold.type = 'button';
    fold.addEventListener('click', () => this.setFolded(!element.classList.contains('folded')));
    title.append(caption, fold);
    const rows = switches.map((viewSwitch) => {
      const label = document.createElement('label');
      label.className = 'switch';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.addEventListener('change', () => viewSwitch.write(input.checked));
      const text = document.createElement('span');
      text.textContent = viewSwitch.label;
      label.append(input, text);
      this.#switches.push({ viewSwitch, input });
      return label;
    });
    this.#objects = document.createElement('ul');
    this.#objects.className = 'layer-objects';
    this.#objects.setAttribute('aria-label', 'Objects');
    element.replaceChildren(title, ...rows, this.#objects);
    this.#fold = fold;
    this.setFolded(false);
    this.refresh();
  }

  /**
   * Show each switch's current state, after a scene set its own.
   */
  refresh() {
    for (const { viewSwitch, input } of this.#switches) input.checked = viewSwitch.read();
  }

  /**
   * @param {boolean} folded Whether the overlay shows only its title.
   */
  setFolded(folded) {
    this.element.classList.toggle('folded', folded);
    this.#fold.textContent = folded ? '▸' : '▾';
    this.#fold.setAttribute('aria-label', folded ? 'Show the layers' : 'Fold the layers');
    this.#fold.setAttribute('aria-expanded', String(!folded));
  }

  /**
   * @param {Array<LayerObject>} objects The scene's free objects.
   */
  showObjects(objects) {
    const document = this.element.ownerDocument;
    this.#objects.replaceChildren(
      ...objects.map((object) => {
        const item = document.createElement('li');
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = object.label;
        button.title = `Light up ${object.label}`;
        button.addEventListener('click', () => this.#onPick(object.key));
        item.append(button);
        return item;
      }),
    );
  }
}
