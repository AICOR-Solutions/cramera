/**
 * Just enough of the DOM for the viewer's parts to build and update their elements
 * in Node: elements with children, attributes, data attributes, text, classes and
 * listeners.
 */

// %% elements

export class FakeElement {
  /**
   * @param {string} tagName The element's tag.
   * @param {FakeDocument} ownerDocument The document that created the element.
   */
  constructor(tagName, ownerDocument) {
    this.tagName = tagName.toUpperCase();
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.parentElement = null;
    this.dataset = {};
    this.attributes = new Map();
    this.listeners = new Map();
    this.textContent = '';
    this.value = '';
    this.hidden = false;
    this.disabled = false;
    this.style = {};
    this.classList = new FakeClassList();
  }

  append(...children) {
    for (const given of children) {
      const child = typeof given === 'string' ? Object.assign(new FakeElement('#text', this.ownerDocument), { textContent: given }) : given;
      child.parentElement = this;
      this.children.push(child);
    }
  }

  replaceChildren(...children) {
    this.children = [];
    this.append(...children);
  }

  remove() {
    if (this.parentElement) this.parentElement.children = this.parentElement.children.filter((child) => child !== this);
    this.parentElement = null;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(listener);
  }

  removeEventListener(type, listener) {
    this.listeners.get(type)?.delete(listener);
  }

  dispatch(type, event = {}) {
    for (const listener of [...(this.listeners.get(type) ?? [])]) listener({ target: this, preventDefault() {}, ...event });
  }

  listenerCount(type) {
    return this.listeners.get(type)?.size ?? 0;
  }

  /**
   * @param {function(FakeElement): boolean} predicate Selects elements.
   * @returns {Array<FakeElement>} Every descendant the predicate selects, in document order.
   */
  findAll(predicate) {
    const found = [];
    for (const child of this.children) {
      if (predicate(child)) found.push(child);
      found.push(...child.findAll(predicate));
    }
    return found;
  }

  /**
   * @returns {string} The text of the element and its descendants.
   */
  get innerText() {
    return [this.textContent, ...this.children.map((child) => child.innerText)].join('');
  }
}

class FakeClassList {
  constructor() {
    this.names = new Set();
  }

  add(...names) {
    names.forEach((name) => this.names.add(name));
  }

  remove(...names) {
    names.forEach((name) => this.names.delete(name));
  }

  toggle(name, force) {
    const present = force ?? !this.names.has(name);
    if (present) this.names.add(name);
    else this.names.delete(name);
    return present;
  }

  contains(name) {
    return this.names.has(name);
  }
}

// %% document

export class FakeDocument {
  constructor() {
    this.documentElement = new FakeElement('html', this);
    this.body = new FakeElement('body', this);
    this.documentElement.append(this.body);
  }

  createElement(tagName) {
    return new FakeElement(tagName, this);
  }
}
