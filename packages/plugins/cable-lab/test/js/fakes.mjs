/**
 * Stand-ins for the cable lab page's elements, its routes, the timers and the page
 * status, for the cable lab's tests.
 */

import { readFileSync } from 'node:fs';

import { CableConfigurationKey, CableLabKey, SimulationLifecycle } from 'cramera-viewer/protocol.js';
import { ElementId } from '../../src/cramera_cable_lab/web/lab/lab-page.js';
import { FakeDocument, FakeElement } from 'cramera-testing/fake-document.mjs';

/**
 * A measured state of a running lab.
 */
export const RUNNING_STATE = JSON.parse(readFileSync(new URL('./running_state.json', import.meta.url), 'utf-8'));

/**
 * The page's markup.
 */
export const PAGE = readFileSync(new URL('../../src/cramera_cable_lab/web/cable-lab.html', import.meta.url), 'utf-8');

/**
 * The gripper actions the page's buttons send.
 */
export const BUTTON_ACTIONS = [...PAGE.matchAll(/data-action="([^"]+)"/g)].map((match) => match[1]);

// %% form

/**
 * A form field: a value, a checked state and a default to reset to.
 */
class FakeField extends FakeElement {
  constructor(document, value, checked) {
    super('input', document);
    this.value = value;
    this.checked = checked;
    this.defaults = { value, checked };
  }
}

/**
 * A form with the configuration's fields at the page's defaults.
 */
export class FakeForm extends FakeElement {
  constructor(document) {
    super('form', document);
    this.elements = {};
    for (const match of PAGE.matchAll(/<input name="([^"]+)" type="([^"]+)"([^>]*)>/g)) {
      const [, name, type, rest] = match;
      const value = /value="([^"]*)"/.exec(rest)?.[1] ?? '';
      this.elements[name] = new FakeField(document, value, type === 'checkbox' && rest.includes('checked'));
    }
  }

  reset() {
    for (const field of Object.values(this.elements)) {
      field.value = field.defaults.value;
      field.checked = field.defaults.checked;
    }
  }
}

// %% page

/**
 * The page's elements by id, its gripper buttons and its form.
 */
export class FakeLabDocument extends FakeDocument {
  constructor() {
    super();
    this.byId = new Map();
    for (const id of Object.values(ElementId)) this.byId.set(id, this.createElement('div'));
    this.byId.set(ElementId.FORM, new FakeForm(this));
    this.buttons = BUTTON_ACTIONS.map((action) => {
      const button = this.createElement('button');
      button.dataset.action = action;
      return button;
    });
  }

  getElementById(id) {
    return this.byId.get(id) ?? null;
  }

  querySelectorAll() {
    return this.buttons;
  }
}

/**
 * Cable lab routes that answer fixed states and record the requests.
 */
export class FakeClient {
  constructor() {
    this.requests = [];
    this.current = { [CableLabKey.LIFECYCLE]: SimulationLifecycle.IDLE };
    this.failure = null;
  }

  async #answer(request, state) {
    this.requests.push(request);
    if (this.failure) throw this.failure;
    this.current = state;
    return state;
  }

  state() {
    return this.#answer(['state'], this.current);
  }

  start(configuration) {
    return this.#answer(['start', configuration], structuredClone(RUNNING_STATE));
  }

  command(command) {
    return this.#answer(['command', command], structuredClone(RUNNING_STATE));
  }

  reset() {
    return this.#answer(['reset'], structuredClone(RUNNING_STATE));
  }

  stop() {
    return this.#answer(['stop'], { ...structuredClone(RUNNING_STATE), [CableLabKey.LIFECYCLE]: SimulationLifecycle.IDLE });
  }
}

/**
 * A 3D view that records what it is asked to show.
 */
export class FakeView {
  constructor() {
    this.shown = [];
    this.pointsShown = false;
    this.needsFraming = false;
  }

  show(state) {
    this.shown.push(state);
  }

  setPointsShown(shown) {
    this.pointsShown = shown;
  }
}

/**
 * Timers that record instead of running.
 */
export class FakeTimers {
  constructor() {
    this.pending = new Map();
    this.next = 1;
  }

  setTimeout(callback, milliseconds) {
    const identifier = this.next++;
    this.pending.set(identifier, { callback, milliseconds });
    return identifier;
  }

  clearTimeout(identifier) {
    this.pending.delete(identifier);
  }
}

/**
 * A page status that records the states it reports.
 */
export class FakeStatus {
  constructor() {
    this.reports = [];
  }

  ready(text) {
    this.reports.push(['ready', text]);
  }

  failed(text) {
    this.reports.push(['failed', text]);
  }
}

/**
 * The configuration keys the form's fields are named by.
 */
export const FORM_FIELDS = Object.keys(new FakeForm(new FakeDocument()).elements);

export { CableConfigurationKey };
