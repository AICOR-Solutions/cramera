/**
 * The cable lab page: builds and stops cables, sends gripper commands, reads the state
 * every tenth of a second and shows the measured forces.
 */

import {
  CableLabKey,
  GraspState,
  GripperCommandKey,
  SimulationLifecycle,
} from '../../../protocol.js';
import { ConfigurationForm } from './configuration-form.js';

/**
 * How often the state is read, in milliseconds.
 */
export const POLL_MILLISECONDS = 100;

/**
 * The decimals the readings are shown with.
 */
const READING_DECIMALS = 2;

/**
 * What the page shows for a reading the state does not have.
 */
const NO_READING = '—';

/**
 * What the status line says in each lifecycle state.
 */
export const LIFECYCLE_TEXT = Object.freeze({
  [SimulationLifecycle.IDLE]: 'No simulation runs',
  [SimulationLifecycle.RUNNING]: 'Simulation running',
  [SimulationLifecycle.FAILED]: 'Simulation failed',
});

/**
 * What the gripper heading says about each grasp state.
 */
export const GRASP_TEXT = Object.freeze({
  [GraspState.OPEN]: 'Gripper open',
  [GraspState.CONTACT]: 'Cable contact',
  [GraspState.HOLDING]: 'Both pads hold, little slip',
  [GraspState.SLIPPING]: 'Cable slipping',
});

/**
 * The page's fixed texts.
 */
const Text = Object.freeze({
  NO_GRASP: 'No contact data',
  CAPTION: 'Measured MuJoCo poses · metres',
  WAITING: 'Waiting for the simulation',
  BUILD: 'Build and start',
  WORKING: 'Working…',
  UNREACHABLE: 'The cable lab cannot be reached',
  SECONDS: ' s',
  NEWTONS: ' N',
  NO_VIEW: 'The 3D view needs WebGL; the readings still come from the live simulation.',
});

/**
 * The ids of the page's elements.
 */
export const ElementId = Object.freeze({
  FORM: 'cable-configuration',
  VIEWPORT: 'cable-viewport',
  STATUS: 'cable-status',
  ERROR: 'cable-error',
  WARNING: 'cable-warning',
  CAPTION: 'cable-caption',
  EMPTY: 'cable-empty',
  POINTS: 'show-points',
  TIME: 'reading-time',
  CONTACTS: 'reading-contacts',
  NORMAL: 'reading-normal',
  FRICTION: 'reading-friction',
  GRASP: 'grasp-state',
  START: 'start-button',
  RESET: 'reset-button',
  STOP: 'stop-button',
  PINNED: 'preset-pinned',
  LOOSE: 'preset-loose',
  FRICTION_VALUE: 'friction-value',
  LENGTH: 'cable-length',
});

/**
 * The data attribute naming a gripper button's action.
 */
const ACTION_ATTRIBUTE = 'action';

// %% page

export class LabPage {
  /**
   * The page.
   * @type {Document}
   */
  #document;

  /**
   * The cable lab routes.
   * @type {import('./cable-client.js').CableLabClient}
   */
  #client;

  /**
   * The 3D view, or null without WebGL.
   * @type {import('./cable-view.js').CableView|null}
   */
  #view;

  /**
   * The browser's timers.
   * @type {{setTimeout: function(function(): void, number): number, clearTimeout: function(number): void}}
   */
  #timers;

  /**
   * Reports how far the page is, for the screenshot command.
   * @type {import('../../../core/page-status.js').PageStatus}
   */
  #status;

  /**
   * The pending state read, or 0.
   * @type {number}
   */
  #timer = 0;

  /**
   * Counts the changes, so a state read sent before one is not shown after it.
   * @type {number}
   */
  #revision = 0;

  /**
   * The configuration form.
   * @type {ConfigurationForm}
   */
  form;

  /**
   * The last state shown.
   * @type {Object}
   */
  state = { [CableLabKey.LIFECYCLE]: SimulationLifecycle.IDLE };

  /**
   * Whether a change is under way.
   * @type {boolean}
   */
  busy = false;

  /**
   * Why the last change failed, or ''.
   * @type {string}
   */
  failure = '';

  /**
   * Whether the page polls.
   * @type {boolean}
   */
  active = true;

  /**
   * @param {Document} document The page.
   * @param {import('./cable-client.js').CableLabClient} client The cable lab routes.
   * @param {import('./cable-view.js').CableView|null} view The 3D view, or null without WebGL.
   * @param {Object} timers The browser's timers.
   * @param {import('../../../core/page-status.js').PageStatus} status Reports how far the page is.
   */
  constructor(document, client, view, timers, status) {
    this.#document = document;
    this.#client = client;
    this.#view = view;
    this.#timers = timers;
    this.#status = status;
    this.form = new ConfigurationForm(this.#element(ElementId.FORM));
    this.#bind();
    this.#showConfiguration();
  }

  /**
   * @param {string} id An `ElementId` value.
   * @returns {HTMLElement} The element.
   */
  #element(id) {
    return this.#document.getElementById(id);
  }

  /**
   * @returns {Array<HTMLButtonElement>} The gripper buttons.
   */
  #gripperButtons() {
    return [...this.#document.querySelectorAll(`[data-${ACTION_ATTRIBUTE}]`)];
  }

  #bind() {
    this.form.form.addEventListener('submit', (event) => {
      event.preventDefault();
      if (this.#view) this.#view.needsFraming = true;
      this.perform(() => this.#client.start(this.form.read()));
    });
    this.form.form.addEventListener('input', () => this.#showConfiguration());
    this.#element(ElementId.PINNED).addEventListener('click', () => this.preset(true));
    this.#element(ElementId.LOOSE).addEventListener('click', () => this.preset(false));
    for (const button of this.#gripperButtons()) {
      button.addEventListener('click', () =>
        this.perform(() => this.#client.command({ [GripperCommandKey.ACTION]: button.dataset[ACTION_ATTRIBUTE] })),
      );
    }
    this.#element(ElementId.RESET).addEventListener('click', () => this.perform(() => this.#client.reset()));
    this.#element(ElementId.STOP).addEventListener('click', () => this.perform(() => this.#client.stop()));
    this.#element(ElementId.POINTS).addEventListener('change', (event) => this.#view?.setPointsShown(event.target.checked));
  }

  /**
   * @param {boolean} anchored Whether the preset pins the first point.
   */
  preset(anchored) {
    this.form.preset(anchored);
    this.#showConfiguration();
  }

  #showConfiguration() {
    this.#element(ElementId.FRICTION_VALUE).value = this.form.frictionText();
    this.#element(ElementId.LENGTH).textContent = this.form.lengthText();
  }

  /**
   * Run one change and show the state it answers.
   * @param {function(): Promise<Object>} change The request.
   * @returns {Promise<void>} Settles once the answer is shown.
   */
  async perform(change) {
    if (this.busy) return;
    this.busy = true;
    this.#revision += 1;
    this.failure = '';
    this.#showButtons();
    const answer = await change().then(
      (state) => ({ state }),
      (error) => ({ error }),
    );
    this.busy = false;
    if (answer.error) this.failure = answer.error.reason ?? answer.error.message;
    else this.show(answer.state);
    this.#showNotices();
    this.#showButtons();
  }

  /**
   * Read the state and show it, then read again after a while.
   * @returns {Promise<void>} Settles once the state is shown.
   */
  async poll() {
    if (!this.active) return;
    const revision = this.#revision;
    const answer = await this.#client.state().then(
      (state) => ({ state }),
      (error) => ({ error }),
    );
    if (answer.error) {
      this.#status.failed(Text.UNREACHABLE);
      this.failure = answer.error.reason ?? answer.error.message;
      this.#showNotices();
    } else if (revision === this.#revision && !this.busy) {
      this.show(answer.state);
    }
    if (this.active) this.#timer = this.#timers.setTimeout(() => this.poll(), POLL_MILLISECONDS);
  }

  /**
   * Stop polling.
   */
  close() {
    this.active = false;
    this.#timers.clearTimeout(this.#timer);
  }

  /**
   * Show a state: readings, grasp, notices, buttons and the 3D view.
   * @param {Object} state The cable lab's state.
   */
  show(state) {
    this.state = state;
    const lifecycle = state[CableLabKey.LIFECYCLE];
    const grasp = state[CableLabKey.GRASP];
    const hasCable = (state[CableLabKey.SEGMENTS] ?? []).length > 0;
    this.#element(ElementId.STATUS).textContent = LIFECYCLE_TEXT[lifecycle];
    this.#element(ElementId.STATUS).dataset.state = lifecycle;
    this.#element(ElementId.GRASP).textContent = grasp ? GRASP_TEXT[grasp[CableLabKey.STATE]] : Text.NO_GRASP;
    this.#element(ElementId.TIME).textContent = this.#reading(state[CableLabKey.SIMULATION_TIME], Text.SECONDS);
    this.#element(ElementId.CONTACTS).textContent = grasp ? String(grasp[CableLabKey.CONTACT_COUNT]) : NO_READING;
    this.#element(ElementId.NORMAL).textContent = this.#reading(grasp?.[CableLabKey.NORMAL_FORCE], Text.NEWTONS);
    this.#element(ElementId.FRICTION).textContent = this.#reading(grasp?.[CableLabKey.FRICTION_FORCE], Text.NEWTONS);
    this.#element(ElementId.EMPTY).hidden = hasCable;
    this.#element(ElementId.CAPTION).textContent = hasCable ? Text.CAPTION : Text.WAITING;
    this.#view?.show(state);
    this.#showNotices();
    this.#showButtons();
    this.#status.ready(LIFECYCLE_TEXT[lifecycle]);
  }

  /**
   * @param {number|undefined} value A measured value.
   * @param {string} unit Its unit.
   * @returns {string} The value as shown.
   */
  #reading(value, unit) {
    return Number.isFinite(value) ? value.toFixed(READING_DECIMALS) + unit : NO_READING;
  }

  #showNotices() {
    const error = this.state[CableLabKey.ERROR] || this.failure;
    this.#element(ElementId.ERROR).textContent = error;
    this.#element(ElementId.ERROR).hidden = !error;
    const warnings = [...(this.#view ? [] : [Text.NO_VIEW]), ...(this.state[CableLabKey.WARNINGS] ?? [])].join(' ');
    this.#element(ElementId.WARNING).textContent = warnings;
    this.#element(ElementId.WARNING).hidden = !warnings;
  }

  #showButtons() {
    const running = this.state[CableLabKey.LIFECYCLE] === SimulationLifecycle.RUNNING;
    for (const button of this.#gripperButtons()) button.disabled = this.busy || !running;
    this.#element(ElementId.START).disabled = this.busy;
    this.#element(ElementId.START).textContent = this.busy ? Text.WORKING : Text.BUILD;
    this.#element(ElementId.RESET).disabled = this.busy || !this.state[CableLabKey.CONFIGURATION];
    this.#element(ElementId.STOP).disabled = this.busy || !running;
  }
}
