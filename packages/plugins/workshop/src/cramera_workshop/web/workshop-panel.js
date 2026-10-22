/**
 * The content of the Workshop side panel for a workshop scene: starts the contact world, holds and moves bodies, drives the
 * drawer motors and the screwdriver, and shows what MuJoCo measures.
 */

import {
  AssetRightsKey,
  DrawerKey,
  DriveDirection,
  ThreadKey,
  WorkshopKey,
  WorkshopStateKey,
  WorkshopView,
} from '../../protocol.js';
import { AlignmentKind, Manipulation } from './workshop-controller.js';

/**
 * Millimetres per metre, for the insertion depth.
 */
const MILLIMETRES = 1000;

/**
 * The decimals the insertion depth is shown with.
 */
const DEPTH_DECIMALS = 1;

/**
 * The share of a drawer's travel past which it counts as open.
 */
const OPEN_SHARE = 0.5;

/**
 * The labels of the camera views.
 */
const VIEW_LABELS = Object.freeze({
  [WorkshopView.OVERVIEW]: 'Overview',
  [WorkshopView.BENCH]: 'Bench',
  [WorkshopView.DRAWERS]: 'Drawers',
});

/**
 * The move buttons: label and offset of the spring target.
 */
const MOVES = Object.freeze([
  ['X −', [-Manipulation.MOVE_STEP, 0, 0]],
  ['X +', [Manipulation.MOVE_STEP, 0, 0]],
  ['Y −', [0, -Manipulation.MOVE_STEP, 0]],
  ['Y +', [0, Manipulation.MOVE_STEP, 0]],
  ['Lower', [0, 0, -Manipulation.MOVE_STEP]],
  ['Lift', [0, 0, Manipulation.MOVE_STEP]],
]);

/**
 * The tilt buttons: axis and name.
 */
const TILTS = Object.freeze([
  [0, 'Roll'],
  [1, 'Pitch'],
  [2, 'Yaw'],
]);

/**
 * The asset rights the panel shows, in order.
 */
const SHOWN_RIGHTS = Object.freeze([
  AssetRightsKey.PRINCIPAL_AUTHOR,
  AssetRightsKey.INSTITUTION,
  AssetRightsKey.COPYRIGHT,
  AssetRightsKey.PERMISSION_NOTICE,
  AssetRightsKey.PRIOR_LICENSE_NOTICE,
]);

/**
 * What the panel's fixed texts say.
 */
const Text = Object.freeze({
  INTRODUCTION: 'Boxes, fasteners, the workpiece and the screwdriver are separate bodies in a MuJoCo contact world. Grab one to lift and tilt it; release it to let gravity act.',
  START: 'Start physics',
  PAUSE: 'Pause physics',
  RESUME: 'Resume physics',
  RESET: 'Reset',
  DRAWERS: 'Drawer motors',
  OPEN: 'Open',
  CLOSE: 'Close',
  OBJECTS: 'Objects and loose contents',
  SELECTED: 'Selected',
  GRAB: 'Grab selected',
  RELEASE: 'Release',
  MOVE_TITLE: 'Move the spring target by 2.5 cm',
  TILT: 'Tilt or turn by 15°',
  SCREW_DRIVING: 'Screw driving',
  SCREW_NOTE: 'Position a screw, then align the driver. Each move lifts above the bench first. The driver turns; an ideal thread couples its measured rotation to the screw\'s travel. No wood is cut.',
  POSITION_SCREW: 'Position screw',
  ALIGN_DRIVER: 'Align driver',
  DRIVE_IN: 'Drive in',
  REVERSE: 'Reverse',
  STOP: 'Stop',
  NOTHING_HELD: 'Nothing held',
  HOLDING: 'Holding: ',
  CONTACTS: ' contacts',
  ENGAGED: 'Driver engaged',
  NOT_ENGAGED: 'Driver not engaged',
  DEPTH: ' mm deep',
  DEMO: 'Watch the recorded PR2 demo',
  RIGHTS: 'Asset rights and credits',
  SEPARATOR: ' · ',
});

// %% rights

/**
 * @param {Document} document The page.
 * @param {Object} rights A bundle's asset rights.
 * @returns {HTMLElement} Who made the assets and on which terms they may be reused.
 */
export function rightsElement(document, rights) {
  const section = document.createElement('details');
  section.className = 'workshop-rights';
  const summary = document.createElement('summary');
  summary.textContent = Text.RIGHTS;
  section.append(summary);
  for (const key of SHOWN_RIGHTS) {
    if (!rights[key]) continue;
    const line = document.createElement('p');
    line.textContent = rights[key];
    section.append(line);
  }
  return section;
}

// %% panel

export class WorkshopPanel {
  /**
   * The page.
   * @type {Document}
   */
  #document;

  /**
   * The workshop description.
   * @type {Object}
   */
  #workshop;

  /**
   * The commands to the contact world.
   * @type {import('./workshop-controller.js').WorkshopController}
   */
  #controller;

  /**
   * Each button with whether it may be pressed now.
   * @type {Array<{button: HTMLButtonElement, enabled: function(): boolean}>}
   */
  #buttons = [];

  /**
   * Each drawer's button by joint.
   * @type {Map<string, HTMLButtonElement>}
   */
  #drawerButtons = new Map();

  /**
   * The panel's content.
   * @type {HTMLElement}
   */
  element;

  /**
   * The start and pause button.
   * @type {HTMLButtonElement}
   */
  run;

  /**
   * The body chooser.
   * @type {HTMLSelectElement}
   */
  chooser;

  /**
   * What the spring holds and how many contacts there are.
   * @type {HTMLElement}
   */
  observation;

  /**
   * The thread's state.
   * @type {HTMLElement}
   */
  threadState;

  /**
   * The status line.
   * @type {HTMLElement}
   */
  status;

  /**
   * The button opening the recorded demo, hidden without one.
   * @type {HTMLButtonElement}
   */
  demo;

  /**
   * @param {Document} document The page.
   * @param {Object} workshop The workshop description of the shown bundle.
   * @param {import('./workshop-controller.js').WorkshopController} controller The commands.
   * @param {Object|null} rights The bundle's asset rights, or null.
   * @param {function(): void} openDemo Shows the recorded demo.
   */
  constructor(document, workshop, controller, rights, openDemo) {
    this.#document = document;
    this.#workshop = workshop;
    this.#controller = controller;
    const root = document.createElement('div');
    root.className = 'workshop-panel';
    this.element = root;
    this.#element('p', root, 'workshop-note', Text.INTRODUCTION);
    this.demo = this.#button(root, Text.DEMO, openDemo, () => true, 'workshop-primary');
    this.demo.hidden = true;
    this.#buildRun(root);
    this.#buildViews(root);
    this.#buildDrawers(root);
    this.#buildObjects(root);
    this.#buildThread(root);
    this.status = this.#element('p', root, 'workshop-status');
    this.status.setAttribute('role', 'status');
    if (rights) root.append(rightsElement(document, rights));
    controller.onChange = () => this.refresh();
    this.refresh();
  }

  // %% building

  /**
   * @param {string} tag An element tag.
   * @param {HTMLElement} parent Where the element goes.
   * @param {string=} className Its class.
   * @param {string=} text Its text.
   * @returns {HTMLElement} The element.
   */
  #element(tag, parent, className, text) {
    const element = this.#document.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    parent.append(element);
    return element;
  }

  /**
   * @param {HTMLElement} parent Where the button goes.
   * @param {string} label Its text.
   * @param {function(): (Promise<Object>|Object|void)} action What it does.
   * @param {function(): boolean=} enabled Whether it may be pressed now.
   * @param {string=} className Its class.
   * @returns {HTMLButtonElement} The button.
   */
  #button(parent, label, action, enabled = () => this.#controller.canManipulate(), className) {
    const button = this.#element('button', parent, className, label);
    button.type = 'button';
    button.addEventListener('click', async () => {
      const outcome = await action();
      if (outcome?.message) this.#controller.message = outcome.message;
      this.refresh();
    });
    this.#buttons.push({ button, enabled });
    return button;
  }

  /**
   * @param {HTMLElement} root The panel's content.
   */
  #buildRun(root) {
    const row = this.#element('div', root, 'workshop-row');
    const controller = this.#controller;
    this.run = this.#button(
      row,
      Text.START,
      () => (controller.isRunning() ? controller.pause() : controller.start()),
      () => !controller.pending && !controller.closed,
      'workshop-primary',
    );
    this.#button(row, Text.RESET, () => controller.reset(), () => controller.isReady() && !controller.pending);
  }

  /**
   * @param {HTMLElement} root The panel's content.
   */
  #buildViews(root) {
    const row = this.#element('div', root, 'workshop-row');
    for (const view of Object.values(WorkshopView)) {
      if (!this.#workshop[WorkshopKey.CAMERAS]?.[view]) continue;
      this.#button(row, VIEW_LABELS[view], () => this.#controller.look(view), () => true);
    }
  }

  /**
   * @param {HTMLElement} root The panel's content.
   */
  #buildDrawers(root) {
    const section = this.#element('fieldset', root, 'workshop-section');
    this.#element('legend', section, null, Text.DRAWERS);
    const controller = this.#controller;
    for (const drawer of this.#workshop[WorkshopKey.DRAWERS] ?? []) {
      const row = this.#element('div', section, 'workshop-row workshop-drawer');
      this.#element('span', row, null, drawer[DrawerKey.LABEL]);
      const button = this.#button(
        row,
        Text.OPEN,
        () => controller.setDrawer(drawer, this.#isOpen(drawer) ? 0 : drawer[DrawerKey.OPEN]),
        () => controller.isRunning() && !controller.aligning,
      );
      this.#drawerButtons.set(drawer[DrawerKey.JOINT], button);
    }
  }

  /**
   * @param {HTMLElement} root The panel's content.
   */
  #buildObjects(root) {
    const section = this.#element('fieldset', root, 'workshop-section');
    this.#element('legend', section, null, Text.OBJECTS);
    const controller = this.#controller;
    const label = this.#element('label', section, 'workshop-chooser');
    this.#element('span', label, null, Text.SELECTED);
    this.chooser = this.#element('select', label);
    for (const [key, name] of controller.labels) {
      const option = this.#element('option', this.chooser, null, name);
      option.value = key;
    }
    this.chooser.addEventListener('change', () => controller.select(this.chooser.value));
    const holding = this.#element('div', section, 'workshop-row');
    this.#button(
      holding,
      Text.GRAB,
      () => controller.grab(),
      () => controller.isRunning() && !controller.pending && !controller.aligning,
      'workshop-primary',
    );
    this.#button(holding, Text.RELEASE, () => controller.release());
    const moves = this.#element('div', section, 'workshop-grid');
    for (const [name, offset] of MOVES) {
      this.#button(moves, name, () => controller.moveBy(offset)).title = Text.MOVE_TITLE;
    }
    const tilts = this.#element('details', section, 'workshop-tilts');
    this.#element('summary', tilts, null, Text.TILT);
    const grid = this.#element('div', tilts, 'workshop-grid');
    for (const [axis, name] of TILTS) {
      this.#button(grid, `${name} −`, () => controller.tilt(axis, -Manipulation.ANGLE_STEP));
      this.#button(grid, `${name} +`, () => controller.tilt(axis, Manipulation.ANGLE_STEP));
    }
    this.observation = this.#element('p', section, 'workshop-note');
  }

  /**
   * @param {HTMLElement} root The panel's content.
   */
  #buildThread(root) {
    const section = this.#element('details', root, 'workshop-section workshop-thread');
    this.#element('summary', section, null, Text.SCREW_DRIVING);
    this.#element('p', section, 'workshop-note', Text.SCREW_NOTE);
    const controller = this.#controller;
    const idle = () => controller.isRunning() && !controller.aligning && !controller.pending;
    const align = this.#element('div', section, 'workshop-row');
    this.#button(align, Text.POSITION_SCREW, () => controller.align(AlignmentKind.SCREW), idle);
    this.#button(align, Text.ALIGN_DRIVER, () => controller.align(AlignmentKind.DRIVER), idle);
    const drive = this.#element('div', section, 'workshop-row');
    this.#button(drive, Text.DRIVE_IN, () => controller.drive(DriveDirection.FORWARD));
    this.#button(drive, Text.REVERSE, () => controller.drive(DriveDirection.REVERSE));
    this.#button(drive, Text.STOP, () => controller.drive(DriveDirection.STOP));
    this.threadState = this.#element('p', section, 'workshop-note');
  }

  // %% showing

  /**
   * @param {Object} drawer A drawer of the workshop description.
   * @returns {boolean} Whether the measured drawer is more open than closed.
   */
  #isOpen(drawer) {
    const position = this.#controller.state?.[WorkshopStateKey.JOINTS]?.[drawer[DrawerKey.JOINT]] ?? 0;
    return position > drawer[DrawerKey.OPEN] * OPEN_SHARE;
  }

  /**
   * Show the controller's state: which buttons work, what is held, the thread.
   */
  refresh() {
    const controller = this.#controller;
    for (const { button, enabled } of this.#buttons) button.disabled = !enabled();
    this.run.textContent = controller.isRunning() ? Text.PAUSE : controller.state ? Text.RESUME : Text.START;
    this.chooser.value = controller.selected ?? '';
    for (const drawer of this.#workshop[WorkshopKey.DRAWERS] ?? []) {
      this.#drawerButtons.get(drawer[DrawerKey.JOINT]).textContent = this.#isOpen(drawer) ? Text.CLOSE : Text.OPEN;
    }
    const state = controller.state ?? {};
    const held = state[WorkshopStateKey.HELD];
    const contacts = (state[WorkshopStateKey.CONTACTS] ?? []).length;
    this.observation.textContent = (held ? Text.HOLDING + controller.label(held) : Text.NOTHING_HELD) + Text.SEPARATOR + contacts + Text.CONTACTS;
    const thread = state[WorkshopStateKey.THREAD];
    this.threadState.textContent = thread
      ? [
        thread[ThreadKey.STATE],
        thread[ThreadKey.ENGAGED] ? Text.ENGAGED : Text.NOT_ENGAGED,
        (thread[ThreadKey.DEPTH] * MILLIMETRES).toFixed(DEPTH_DECIMALS) + Text.DEPTH,
      ].join(Text.SEPARATOR)
      : '';
    this.status.textContent = controller.error ?? controller.message;
    this.status.dataset.error = String(controller.error !== null);
  }

  /**
   * @param {boolean} available Whether the recorded demo can be shown.
   */
  offerDemo(available) {
    this.demo.hidden = !available;
  }
}
