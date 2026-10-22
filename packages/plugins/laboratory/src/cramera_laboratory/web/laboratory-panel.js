/**
 * The Laboratory side panel: the shipped laboratories to open or simulate, the device
 * catalog, and while a simulation is shown, its controls and what it measures.
 */

import { SidePanel } from '../../panels/panel-host.js';
import {
  TaskRunKey,
  TaskRunState,
  BenchDrawerStateKey,
  BenchKey,
  CameraKey,
  CentrifugeAction,
  CentrifugeRequestKey,
  CentrifugeStateKey,
  CycleLimitsKey,
  DeviceCatalogKey,
  DeviceEntryKey,
  DispenserAction,
  DispenserRequestKey,
  DispenserState,
  DoseKey,
  DoseLimitsKey,
  EvaluationKey,
  InstalledLaboratoryKey,
  InstrumentCollectionKey,
  InstrumentKey,
  InstrumentPose,
  InstrumentRequestKey,
  KnowledgeKey,
  LaboratoryCatalogKey,
  LaboratoryChoiceKey,
  LaboratoryEntryKey,
  LaboratoryName,
  LaboratoryRoute,
  LaboratorySceneKey,
  LiquidRequestKey,
  LiquidStateKey,
  ManualEdition,
  ManualKey,
  ManualRequestKey,
  OpeningAction,
  OpeningRequestKey,
  PuddleKey,
  ReagentKey,
  RefrigeratorStateKey,
  RequirementKey,
  ReservoirKey,
  RotorHolderKey,
  ScaleReadingKey,
  SimulationAnswerKey,
  SimulationState,
  SnapshotKey,
  StoragePositionKey,
  TargetRequestKey,
  ContactPhysicsKey,
  DropletKey,
  VesselLiquidKey,
  WorkstationKey,
} from '../../protocol.js';

/**
 * How far one press of a move button shifts the pull target, in metres.
 */
export const MOVE_STEP = 0.01;

/**
 * The initial value and step of the panel's number fields: the fill in millilitres, the
 * rotor speed in revolutions per minute, the cycle length in seconds and the dose in
 * millilitres.
 */
const FieldStep = Object.freeze({ FILL: 0.5, FILL_DEFAULT: 1, SPEED: 10, DURATION: 1, DOSE: 0.1 });

/**
 * Where the camera stands relative to an object it looks at closely, in metres.
 */
export const LOOK_OFFSET = Object.freeze([0.25, -0.35, 0.2]);

/**
 * The decimals a volume, a mass and a force are shown with.
 */
const Decimals = Object.freeze({ VOLUME: 2, MASS: 3, FORCE: 3, TIME: 1, SPEED: 0, TEMPERATURE: 1, POSITION: 3 });

/**
 * The texts the panel shows.
 */
export const Text = Object.freeze({
  TITLE: 'Laboratory',
  LABORATORIES: 'Laboratories',
  OPEN: 'Open',
  SIMULATE: 'Simulate with contact physics',
  NO_PHYSICS: 'The contact simulation needs MuJoCo on the server (cramera-laboratory[physics]).',
  INSTRUMENTS: 'instruments',
  DEVICES: 'Devices',
  DEVICE_FILE: 'URDF',
  SIMULATION: 'Contact simulation',
  NOT_SHOWN: 'Open a laboratory’s contact simulation to operate it here.',
  STOP: 'Stop simulation',
  RESET: 'Reset laboratory',
  OBJECT: 'Object',
  LEFT: '← x',
  RIGHT: 'x →',
  BACK: 'y +',
  FRONT: 'y −',
  LIFT: 'Lift',
  LOWER: 'Lower',
  RELEASE: 'Let go',
  FILL: 'Set fill (ml)',
  SCALE: 'Scale',
  TARE: 'Tare',
  STABLE: 'stable',
  SETTLING: 'settling',
  CENTRIFUGE: 'Centrifuge',
  OPEN_LID: 'Open lid',
  CLOSE_LID: 'Close lid',
  SECURE: 'Secure selected vessel',
  RELEASE_HOLDER: 'Release holder',
  START: 'Start cycle',
  STOP_ROTOR: 'Stop rotor',
  MANUAL: 'Read manual',
  REFRIGERATOR: 'Sample refrigerator',
  OPEN_DOOR: 'Open door',
  CLOSE_DOOR: 'Close door',
  DRAWER: 'Drawer',
  OPEN_DRAWER: 'Open drawer',
  CLOSE_DRAWER: 'Close drawer',
  DISPENSER: 'Dispensing station',
  DISPENSE: 'Dispense into selected vessel',
  STOP_DOSE: 'Stop',
  RESUME: 'Resume',
  REFILL: 'Refill',
  INSTRUMENT_COLLECTION: 'Instruments',
  INSPECT: 'Inspection pose',
  REST: 'Rest pose',
  EMPTY: '—',
  TRANSFER: 'PR2 vessel transfer (CRAM)',
  RUN: 'Run the demo',
  OPEN_RECORDING: 'Open the recording',
  END_RUN: 'End the run',
  LID_OPEN: 'lid open',
  LID_CLOSED: 'lid closed',
  LID_MOVING: 'lid moving',
  BALANCED: 'balanced',
  UNBALANCED: 'not balanced',
  READY: 'ready',
  MISSING: 'missing',
  DOOR_OPEN: 'door open',
  DOOR_CLOSED: 'door closed',
  DOOR_MOVING: 'door moving',
  CABINET_EMPTY: 'empty',
  VIEW: 'View',
  LOOK: 'Look at selected object',
});

/**
 * The CSS classes of the panel's parts.
 */
const Style = Object.freeze({
  PANEL: 'laboratory-panel',
  SECTION: 'laboratory-section',
  ROW: 'laboratory-row',
  FACTS: 'laboratory-facts',
  MESSAGE: 'laboratory-message',
  ERROR: 'laboratory-error',
  NOTE: 'laboratory-note',
});

// %% elements

class ElementFactory {
  /**
   * The page.
   * @type {Document}
   */
  #document;

  /**
   * @param {Document} document The page.
   */
  constructor(document) {
    this.#document = document;
  }

  /**
   * @param {string} tag An element tag.
   * @param {string=} text Its text.
   * @param {string=} className Its CSS class.
   * @returns {HTMLElement} The element.
   */
  element(tag, text = '', className = '') {
    const element = this.#document.createElement(tag);
    if (text) element.textContent = text;
    if (className) element.className = className;
    return element;
  }

  /**
   * @param {string} text The button's text.
   * @param {function(): void} onClick Called when it is pressed.
   * @returns {HTMLButtonElement} The button.
   */
  button(text, onClick) {
    const button = this.element('button', text);
    button.type = 'button';
    button.addEventListener('click', onClick);
    return button;
  }

  /**
   * @param {Array<string>} values The choices.
   * @returns {HTMLSelectElement} A select of the choices.
   */
  select(values) {
    const select = this.element('select');
    for (const value of values) {
      const option = this.element('option', value);
      option.value = value;
      select.append(option);
    }
    select.value = values[0] ?? '';
    return select;
  }

  /**
   * @param {number} value The initial number.
   * @param {number} step The step of the number's arrows.
   * @returns {HTMLInputElement} A number input.
   */
  number(value, step) {
    const input = this.element('input');
    input.type = 'number';
    input.step = String(step);
    input.value = String(value);
    return input;
  }

  /**
   * @param {...HTMLElement} children The row's elements.
   * @returns {HTMLElement} A row of them.
   */
  row(...children) {
    const row = this.element('div', '', Style.ROW);
    row.append(...children);
    return row;
  }
}

/**
 * @param {number|null|undefined} value A number, or nothing.
 * @param {number} decimals The decimals to show.
 * @returns {string} The number as shown.
 */
export function formatted(value, decimals) {
  return value === null || value === undefined ? Text.EMPTY : Number(value).toFixed(decimals);
}

// %% panel

export class LaboratoryPanel {
  /**
   * The side panel.
   * @type {SidePanel}
   */
  panel;

  /**
   * Builds the panel's elements.
   * @type {ElementFactory}
   */
  #elements;

  /**
   * The laboratory's routes.
   * @type {import('./laboratory-client.js').LaboratoryClient}
   */
  #client;

  /**
   * Shows a bundle: asks the viewer for it, or loads the page anew for a bundle the
   * page does not list yet.
   * @type {function(string): void}
   */
  #showScene;

  /**
   * The laboratories part.
   * @type {HTMLElement}
   */
  laboratories;

  /**
   * The devices part.
   * @type {HTMLElement}
   */
  devices;

  /**
   * The task demo part.
   * @type {HTMLElement}
   */
  demos;

  /**
   * The simulation part.
   * @type {HTMLElement}
   */
  simulation;

  /**
   * The message line.
   * @type {HTMLElement}
   */
  message;

  /**
   * The simulation's status line, while a simulation is shown.
   * @type {HTMLElement|null}
   */
  status = null;

  /**
   * The controls the simulation part is built for, null while none is shown.
   * @type {Object|null}
   */
  #controls = null;

  /**
   * Updates the simulation part's measurements from a snapshot.
   * @type {Array<function(Object): void>}
   */
  #updates = [];

  /**
   * The object the move and fill buttons act on.
   * @type {HTMLSelectElement|null}
   */
  objectChoice = null;

  /**
   * The latest snapshot shown.
   * @type {Object|null}
   */
  snapshot = null;

  /**
   * Points the camera from a position at a target.
   * @type {function(Array<number>, Array<number>): void}
   */
  #lookFrom;

  /**
   * @param {Document} document The page.
   * @param {import('./laboratory-client.js').LaboratoryClient} client The laboratory's routes.
   * @param {function(string): void} showScene Shows a bundle.
   * @param {function(Array<number>, Array<number>): void} lookFrom Points the camera from a position at a target.
   */
  constructor(document, client, showScene, lookFrom) {
    this.#elements = new ElementFactory(document);
    this.#client = client;
    this.#showScene = showScene;
    this.#lookFrom = lookFrom;
    const root = this.#elements.element('section', '', Style.PANEL);
    this.message = this.#elements.element('p', '', Style.MESSAGE);
    this.message.setAttribute('role', 'status');
    this.laboratories = this.#elements.element('div', '', Style.SECTION);
    this.simulation = this.#elements.element('div', '', Style.SECTION);
    this.devices = this.#elements.element('div', '', Style.SECTION);
    this.demos = this.#elements.element('div', '', Style.SECTION);
    this.simulation.append(this.#elements.element('h2', Text.SIMULATION), this.#elements.element('p', Text.NOT_SHOWN, Style.NOTE));
    root.append(this.message, this.laboratories, this.demos, this.simulation, this.devices);
    this.panel = new SidePanel(LaboratoryName.PLUGIN, Text.TITLE, root);
  }

  // %% messages

  /**
   * @param {string} text What to tell.
   * @param {boolean} error Whether it is an error.
   */
  showMessage(text, error) {
    this.message.textContent = text;
    this.message.classList.toggle(Style.ERROR, error);
  }

  /**
   * Run an action, showing its error if it fails. The request is the boundary where a
   * refused command becomes a message, so its error is caught here.
   * @param {function(): Promise<*>} action The action.
   * @returns {Promise<*>} What it returned, or null when it failed.
   */
  async attempt(action) {
    try {
      const result = await action();
      this.showMessage('', false);
      return result;
    } catch (error) {
      this.showMessage(error.reason ?? error.message, true);
      return null;
    }
  }

  /**
   * Send a command and show the state it answers.
   * @param {string} route The command's route.
   * @param {Object=} body The request document.
   * @returns {Promise<Object|null>} The answer, or null when it was refused.
   */
  command(route, body = {}) {
    return this.attempt(async () => {
      const answer = await this.#client.send(route, body);
      if (this.#controls) this.showAnswer(answer, this.#controls);
      return answer;
    });
  }

  // %% laboratories

  /**
   * @param {Object} catalog The shipped laboratories, keyed by `LaboratoryCatalogKey`.
   */
  showLaboratories(catalog) {
    const physics = catalog[LaboratoryCatalogKey.PHYSICS_AVAILABLE];
    const list = this.#elements.element('ul');
    for (const entry of catalog[LaboratoryCatalogKey.LABORATORIES]) {
      const name = entry[LaboratoryEntryKey.NAME];
      const choice = { [LaboratoryChoiceKey.LABORATORY]: name };
      const count = entry[LaboratoryEntryKey.INSTRUMENTS];
      const item = this.#elements.element('li');
      const title = this.#elements.element('strong', entry[LaboratoryEntryKey.TITLE]);
      const detail = this.#elements.element('span', count ? ` · ${count} ${Text.INSTRUMENTS}` : '', Style.NOTE);
      const open = this.#elements.button(Text.OPEN, () => this.install(choice));
      const simulate = this.#elements.button(Text.SIMULATE, () => this.simulate(choice));
      simulate.disabled = !physics;
      item.append(title, detail, this.#elements.row(open, simulate));
      list.append(item);
    }
    this.laboratories.replaceChildren(this.#elements.element('h2', Text.LABORATORIES), list);
    if (!physics) this.laboratories.append(this.#elements.element('p', Text.NO_PHYSICS, Style.NOTE));
  }

  /**
   * Install a laboratory and show it.
   * @param {Object} choice The laboratory, keyed by `LaboratoryChoiceKey`.
   * @returns {Promise<void>} Settles once the laboratory is shown or refused.
   */
  async install(choice) {
    const installed = await this.attempt(() => this.#client.send(LaboratoryRoute.INSTALL, choice));
    if (installed) this.#showScene(installed[InstalledLaboratoryKey.SCENE]);
  }

  /**
   * Start a laboratory's simulation and show it.
   * @param {Object} choice The laboratory, keyed by `LaboratoryChoiceKey`.
   * @returns {Promise<void>} Settles once the simulation is shown or refused.
   */
  async simulate(choice) {
    const started = await this.attempt(() => this.#client.send(LaboratoryRoute.START, choice));
    if (started) this.#showScene(started[SimulationAnswerKey.SCENE]);
  }

  // %% task demos

  /**
   * Show the transfer demo's state with the actions it allows.
   * @param {Object} run The demo's state, keyed by `TaskRunKey`.
   * @param {function(): void} onStarted Called once a run started, to follow it.
   */
  showTransfer(run, onStarted) {
    const elements = this.#elements;
    const state = run[TaskRunKey.STATE];
    const scene = run[TaskRunKey.SCENE];
    const actions = elements.row();
    if (state === TaskRunState.IDLE || state === TaskRunState.FAILED) {
      actions.append(
        elements.button(Text.RUN, async () => {
          const started = await this.attempt(() => this.#client.send(LaboratoryRoute.TRANSFER_START));
          if (started) {
            this.showTransfer(started, onStarted);
            onStarted();
          }
        }),
      );
    }
    if (state === TaskRunState.RUNNING) {
      actions.append(elements.button(Text.END_RUN, async () => {
        const stopped = await this.attempt(() => this.#client.send(LaboratoryRoute.TRANSFER_STOP));
        if (stopped) this.showTransfer(stopped, onStarted);
      }));
    }
    if (state === TaskRunState.RECORDED) actions.append(elements.button(Text.OPEN_RECORDING, () => this.#showScene(scene)));
    const parts = [elements.element('h2', Text.TRANSFER), elements.element('p', `${state} \u00b7 ${scene}`, Style.NOTE), actions];
    if (run[TaskRunKey.ERROR]) parts.push(elements.element('pre', run[TaskRunKey.ERROR], Style.FACTS));
    this.demos.replaceChildren(...parts);
  }

  // %% devices

  /**
   * @param {Object} catalog The device catalog, keyed by `DeviceCatalogKey`.
   */
  showDevices(catalog) {
    const list = this.#elements.element('ul');
    for (const device of catalog[DeviceCatalogKey.DEVICES]) {
      const item = this.#elements.element('li', `${device[DeviceEntryKey.TITLE]} `);
      const link = this.#elements.element('a', Text.DEVICE_FILE);
      link.href = this.#client.deviceFileUrl(device[DeviceEntryKey.NAME], device[DeviceEntryKey.DESCRIPTION]);
      link.setAttribute('download', '');
      item.append(link);
      list.append(item);
    }
    this.devices.replaceChildren(this.#elements.element('h2', Text.DEVICES), list);
  }

  // %% simulation

  /**
   * Forget the shown simulation.
   */
  hideSimulation() {
    this.#controls = null;
    this.#updates = [];
    this.objectChoice = null;
    this.snapshot = null;
    this.simulation.replaceChildren(this.#elements.element('h2', Text.SIMULATION), this.#elements.element('p', Text.NOT_SHOWN, Style.NOTE));
  }

  /**
   * Show the state of the shown simulation, building its controls once.
   * @param {Object} answer The simulation's state, keyed by `SimulationAnswerKey`.
   * @param {Object} controls The simulation's controls, keyed by `ContactPhysicsKey`.
   * @param {Object=} description The shown scene's description, for the instruments.
   */
  showAnswer(answer, controls, description = null) {
    if (controls !== this.#controls) this.#build(controls, answer, description);
    const snapshot = answer[SimulationAnswerKey.SNAPSHOT];
    this.status.textContent = this.#statusLine(answer);
    if (!snapshot) return;
    this.snapshot = snapshot;
    for (const update of this.#updates) update(snapshot);
  }

  /**
   * @param {Object} answer The simulation's state.
   * @returns {string} The status line.
   */
  #statusLine(answer) {
    const state = answer[SimulationAnswerKey.STATE];
    const snapshot = answer[SimulationAnswerKey.SNAPSHOT];
    if (state === SimulationState.FAILED) return `${state}: ${answer[SimulationAnswerKey.ERROR]}`;
    if (!snapshot) return state;
    return (
      `${state} · t ${formatted(snapshot[SnapshotKey.TIME], Decimals.TIME)} s · ` +
      `pull ${formatted(snapshot[SnapshotKey.APPLIED_FORCE], Decimals.FORCE)} N · ` +
      `${snapshot[SnapshotKey.CONTACTS].length} contacts`
    );
  }

  /**
   * Build the controls of a simulation.
   * @param {Object} controls The simulation's controls.
   * @param {Object} answer Its first state.
   * @param {Object|null} description The shown scene's description.
   */
  #build(controls, answer, description) {
    this.#controls = controls;
    this.#updates = [];
    const elements = this.#elements;
    const snapshot = answer[SimulationAnswerKey.SNAPSHOT] ?? {};
    this.status = elements.element('p', '', Style.NOTE);
    const parts = [
      elements.element('h2', Text.SIMULATION),
      this.status,
      elements.row(
        elements.button(Text.RESET, () => this.command(LaboratoryRoute.RESET)),
        elements.button(Text.STOP, () => this.command(LaboratoryRoute.STOP)),
      ),
      this.#viewSection(description),
      this.#objectSection(controls),
    ];
    if (snapshot[SnapshotKey.SCALE]) parts.push(this.#scaleSection());
    if (controls[ContactPhysicsKey.CYCLES]) parts.push(this.#centrifugeSection(controls));
    if (snapshot[SnapshotKey.REFRIGERATOR]) parts.push(this.#refrigeratorSection());
    if (snapshot[SnapshotKey.DRAWER]) parts.push(this.#drawerSection());
    if (controls[ContactPhysicsKey.DOSES]) parts.push(this.#dispenserSection(controls));
    const collection = description?.[LaboratorySceneKey.INSTRUMENTS];
    if (collection) parts.push(this.#instrumentSection(collection));
    this.simulation.replaceChildren(...parts);
  }

  /**
   * @param {string} title The section's heading.
   * @param {...HTMLElement} children Its elements.
   * @returns {HTMLElement} The section.
   */
  #section(title, ...children) {
    const section = this.#elements.element('section', '', Style.SECTION);
    section.append(this.#elements.element('h3', title), ...children);
    return section;
  }

  /**
   * @param {function(Object): string} text What a fact shows of a snapshot.
   * @returns {HTMLElement} An element showing it, updated with each snapshot.
   */
  #fact(text) {
    const element = this.#elements.element('p', '', Style.FACTS);
    this.#updates.push((snapshot) => {
      element.textContent = text(snapshot);
    });
    return element;
  }

  /**
   * @returns {string} The key of the object the controls act on.
   */
  selectedObject() {
    return this.objectChoice.value;
  }

  /**
   * Shift the pull target of the selected object.
   * @param {Array<number>} offset How far, along x, y and z, in metres.
   * @returns {Promise<Object|null>} The answer.
   */
  move(offset) {
    const key = this.selectedObject();
    const target = this.snapshot?.[SnapshotKey.TARGET];
    const base = target && target[TargetRequestKey.KEY] === key ? target[TargetRequestKey.POSITION] : this.snapshot[SnapshotKey.OBJECTS][key].slice(0, 3);
    const position = base.map((value, axis) => value + offset[axis]);
    return this.command(LaboratoryRoute.TARGET, { [TargetRequestKey.KEY]: key, [TargetRequestKey.POSITION]: position });
  }

  /**
   * @param {Object|null} description The shown scene's description.
   * @returns {HTMLElement} The view section: the bench's camera presets and a close look
   *   at the selected object.
   */
  #viewSection(description) {
    const elements = this.#elements;
    const cameras = Object.entries(description?.[LaboratorySceneKey.LABORATORY]?.[BenchKey.CAMERAS] ?? {});
    const stations = description?.[LaboratorySceneKey.INSTRUMENTS]?.[InstrumentCollectionKey.STATIONS] ?? [];
    for (const station of stations) cameras.push([station[WorkstationKey.LABEL], station[WorkstationKey.CAMERA]]);
    const presets = cameras.map(([name, camera]) =>
      elements.button(name, () => this.#lookFrom(camera[CameraKey.POSITION], camera[CameraKey.TARGET])),
    );
    const object = elements.button(Text.LOOK, () => {
      const position = this.snapshot[SnapshotKey.OBJECTS][this.selectedObject()].slice(0, 3);
      this.#lookFrom(position.map((value, axis) => value + LOOK_OFFSET[axis]), position);
    });
    return this.#section(Text.VIEW, elements.row(...presets, object));
  }

  /**
   * @param {Object} controls The simulation's controls.
   * @returns {HTMLElement} The object section: choice, moves, letting go, filling.
   */
  #objectSection(controls) {
    const elements = this.#elements;
    this.objectChoice = elements.select(controls[ContactPhysicsKey.OBJECTS]);
    const step = MOVE_STEP;
    const volume = elements.number(FieldStep.FILL_DEFAULT, FieldStep.FILL);
    const moves = elements.row(
      elements.button(Text.LEFT, () => this.move([-step, 0, 0])),
      elements.button(Text.RIGHT, () => this.move([step, 0, 0])),
      elements.button(Text.FRONT, () => this.move([0, -step, 0])),
      elements.button(Text.BACK, () => this.move([0, step, 0])),
      elements.button(Text.LIFT, () => this.move([0, 0, step])),
      elements.button(Text.LOWER, () => this.move([0, 0, -step])),
    );
    const fill = elements.row(
      volume,
      elements.button(Text.FILL, () =>
        this.command(LaboratoryRoute.LIQUID, { [LiquidRequestKey.KEY]: this.selectedObject(), [LiquidRequestKey.VOLUME]: Number(volume.value) }),
      ),
    );
    const facts = this.#fact((snapshot) => {
      const liquid = snapshot[SnapshotKey.LIQUID];
      const content = liquid[LiquidStateKey.VESSELS][this.selectedObject()];
      const spilled = liquid[LiquidStateKey.PUDDLES].reduce((sum, puddle) => sum + puddle[PuddleKey.VOLUME], 0);
      const flying = liquid[LiquidStateKey.DROPLETS].reduce((sum, droplet) => sum + droplet[DropletKey.VOLUME], 0);
      const held = content ? `${formatted(content[VesselLiquidKey.VOLUME], Decimals.VOLUME)} ml held · ` : '';
      return `${held}${formatted(spilled, Decimals.VOLUME)} ml spilled · ${formatted(flying, Decimals.VOLUME)} ml in flight`;
    });
    return this.#section(
      Text.OBJECT,
      this.objectChoice,
      moves,
      elements.row(elements.button(Text.RELEASE, () => this.command(LaboratoryRoute.RELEASE))),
      fill,
      facts,
    );
  }

  /**
   * @returns {HTMLElement} The scale section.
   */
  #scaleSection() {
    const reading = this.#fact((snapshot) => {
      const scale = snapshot[SnapshotKey.SCALE];
      const settled = scale[ScaleReadingKey.STABLE] ? Text.STABLE : Text.SETTLING;
      return `${formatted(scale[ScaleReadingKey.GRAMS], Decimals.MASS)} g (${settled}) · ${scale[ScaleReadingKey.OBJECTS].join(', ')}`;
    });
    return this.#section(Text.SCALE, reading, this.#elements.row(this.#elements.button(Text.TARE, () => this.command(LaboratoryRoute.TARE))));
  }

  /**
   * @param {Object} controls The simulation's controls.
   * @returns {HTMLElement} The centrifuge section.
   */
  #centrifugeSection(controls) {
    const elements = this.#elements;
    const cycles = controls[ContactPhysicsKey.CYCLES];
    const holder = elements.select([]);
    const speed = elements.number(cycles[CycleLimitsKey.DEFAULT_SPEED], FieldStep.SPEED);
    const duration = elements.number(cycles[CycleLimitsKey.DEFAULT_DURATION], FieldStep.DURATION);
    const edition = elements.select(Object.values(ManualEdition));
    const send = (body) => this.command(LaboratoryRoute.CENTRIFUGE, body);
    const action = (name) => ({ [CentrifugeRequestKey.ACTION]: name });
    const state = this.#fact((snapshot) => {
      const centrifuge = snapshot[SnapshotKey.CENTRIFUGE];
      const lid = centrifuge[CentrifugeStateKey.LID_OPEN] ? Text.LID_OPEN : centrifuge[CentrifugeStateKey.LID_CLOSED] ? Text.LID_CLOSED : Text.LID_MOVING;
      return (
        `${formatted(centrifuge[CentrifugeStateKey.SPEED], Decimals.SPEED)} rpm · ` +
        `${formatted(centrifuge[CentrifugeStateKey.RELATIVE_FORCE], Decimals.MASS)} × g · ${lid} · ` +
        `${centrifuge[CentrifugeStateKey.BALANCED] ? Text.BALANCED : Text.UNBALANCED} · ` +
        `${formatted(centrifuge[CentrifugeStateKey.REMAINING], Decimals.TIME)} s left`
      );
    });
    const holders = this.#fact((snapshot) => {
      const entries = snapshot[SnapshotKey.CENTRIFUGE][CentrifugeStateKey.HOLDERS];
      if (holder.children.length !== entries.length) {
        holder.replaceChildren(...entries.map((entry) => Object.assign(elements.element('option', entry[RotorHolderKey.IDENTIFIER]), { value: entry[RotorHolderKey.IDENTIFIER] })));
        holder.value = entries[0]?.[RotorHolderKey.IDENTIFIER] ?? '';
      }
      return entries
        .map((entry) => `${entry[RotorHolderKey.IDENTIFIER]}: ${entry[RotorHolderKey.KEY] ?? Text.EMPTY} ${formatted(entry[RotorHolderKey.GRAMS], Decimals.MASS)} g`)
        .join(' · ');
    });
    const knowledge = this.#fact((snapshot) => {
      const known = snapshot[SnapshotKey.CENTRIFUGE][CentrifugeStateKey.KNOWLEDGE];
      const manual = known[KnowledgeKey.MANUAL];
      const evaluation = known[KnowledgeKey.EVALUATION];
      const unmet = evaluation[EvaluationKey.REQUIREMENTS].filter((requirement) => requirement[RequirementKey.SATISFIED] === false);
      return (
        `Manual ${manual[ManualKey.VERSION]}: at least ${manual[ManualKey.MINIMUM_SAMPLES]} samples · ` +
        `${unmet.length ? `${Text.MISSING}: ${unmet.map((requirement) => requirement[RequirementKey.NAME]).join(', ')}` : Text.READY} · ` +
        evaluation[EvaluationKey.NEXT_STEPS].join(' ')
      );
    });
    return this.#section(
      Text.CENTRIFUGE,
      state,
      holders,
      elements.row(
        elements.button(Text.OPEN_LID, () => send(action(CentrifugeAction.OPEN))),
        elements.button(Text.CLOSE_LID, () => send(action(CentrifugeAction.CLOSE))),
      ),
      elements.row(
        holder,
        elements.button(Text.SECURE, () =>
          send({ ...action(CentrifugeAction.SECURE), [CentrifugeRequestKey.SLOT]: holder.value, [CentrifugeRequestKey.KEY]: this.selectedObject() }),
        ),
        elements.button(Text.RELEASE_HOLDER, () => send({ ...action(CentrifugeAction.RELEASE), [CentrifugeRequestKey.SLOT]: holder.value })),
      ),
      elements.row(
        speed,
        duration,
        elements.button(Text.START, () =>
          send({ ...action(CentrifugeAction.START), [CentrifugeRequestKey.SPEED]: Number(speed.value), [CentrifugeRequestKey.DURATION]: Number(duration.value) }),
        ),
        elements.button(Text.STOP_ROTOR, () => send(action(CentrifugeAction.STOP))),
      ),
      knowledge,
      elements.row(
        edition,
        elements.button(Text.MANUAL, () => this.command(LaboratoryRoute.MANUAL, { [ManualRequestKey.EDITION]: edition.value })),
      ),
    );
  }

  /**
   * @returns {HTMLElement} The refrigerator section.
   */
  #refrigeratorSection() {
    const send = (name) => this.command(LaboratoryRoute.REFRIGERATOR, { [OpeningRequestKey.ACTION]: name });
    const state = this.#fact((snapshot) => {
      const refrigerator = snapshot[SnapshotKey.REFRIGERATOR];
      const door = refrigerator[RefrigeratorStateKey.DOOR_OPEN] ? Text.DOOR_OPEN : refrigerator[RefrigeratorStateKey.DOOR_CLOSED] ? Text.DOOR_CLOSED : Text.DOOR_MOVING;
      const stored = refrigerator[RefrigeratorStateKey.POSITIONS]
        .filter((position) => position[StoragePositionKey.KEY])
        .map((position) => `${position[StoragePositionKey.IDENTIFIER]}: ${position[StoragePositionKey.KEY]}`);
      return `${formatted(refrigerator[RefrigeratorStateKey.TEMPERATURE], Decimals.TEMPERATURE)} °C (simulated) · ${door} · ${stored.join(', ') || Text.CABINET_EMPTY}`;
    });
    return this.#section(
      Text.REFRIGERATOR,
      state,
      this.#elements.row(this.#elements.button(Text.OPEN_DOOR, () => send(OpeningAction.OPEN)), this.#elements.button(Text.CLOSE_DOOR, () => send(OpeningAction.CLOSE))),
    );
  }

  /**
   * @returns {HTMLElement} The drawer section.
   */
  #drawerSection() {
    const send = (name) => this.command(LaboratoryRoute.DRAWER, { [OpeningRequestKey.ACTION]: name });
    const state = this.#fact((snapshot) => `${formatted(snapshot[SnapshotKey.DRAWER][BenchDrawerStateKey.POSITION], Decimals.POSITION)} m out`);
    return this.#section(
      Text.DRAWER,
      state,
      this.#elements.row(this.#elements.button(Text.OPEN_DRAWER, () => send(OpeningAction.OPEN)), this.#elements.button(Text.CLOSE_DRAWER, () => send(OpeningAction.CLOSE))),
    );
  }

  /**
   * @param {Object} controls The simulation's controls.
   * @returns {HTMLElement} The dispensing station section.
   */
  #dispenserSection(controls) {
    const elements = this.#elements;
    const doses = controls[ContactPhysicsKey.DOSES];
    const channel = elements.select(doses[DoseLimitsKey.REAGENTS].map((reagent) => reagent[ReagentKey.IDENTIFIER]));
    const dose = elements.number(doses[DoseLimitsKey.DEFAULT], FieldStep.DOSE);
    const send = (body) => this.command(LaboratoryRoute.DISPENSER, body);
    const state = this.#fact((snapshot) => {
      const dispenser = snapshot[SnapshotKey.DISPENSER];
      const reservoirs = dispenser[DoseKey.RESERVOIRS].map((reservoir) => `${reservoir[ReservoirKey.IDENTIFIER]} ${formatted(reservoir[ReservoirKey.VOLUME], Decimals.VOLUME)} ml`);
      const blocked = dispenser[DoseKey.STATE] === DispenserState.BLOCKED ? ` · ${dispenser[DoseKey.BLOCKED_BY]}` : '';
      return (
        `${dispenser[DoseKey.STATE]} · ${formatted(dispenser[DoseKey.DELIVERED], Decimals.VOLUME)} of ` +
        `${formatted(dispenser[DoseKey.REQUESTED], Decimals.VOLUME)} ml · ${reservoirs.join(', ')}${blocked}`
      );
    });
    const action = (name) => ({ [DispenserRequestKey.ACTION]: name });
    return this.#section(
      Text.DISPENSER,
      state,
      elements.row(
        channel,
        dose,
        elements.button(Text.DISPENSE, () =>
          send({ ...action(DispenserAction.DISPENSE), [DispenserRequestKey.KEY]: this.selectedObject(), [DispenserRequestKey.CHANNEL]: channel.value, [DispenserRequestKey.VOLUME]: Number(dose.value) }),
        ),
      ),
      elements.row(
        elements.button(Text.STOP_DOSE, () => send(action(DispenserAction.STOP))),
        elements.button(Text.RESUME, () => send(action(DispenserAction.RESUME))),
        elements.button(Text.REFILL, () => send({ ...action(DispenserAction.REFILL), [DispenserRequestKey.CHANNEL]: channel.value })),
      ),
    );
  }

  /**
   * @param {Object} collection The instrument collection, keyed by `InstrumentCollectionKey`.
   * @returns {HTMLElement} The instrument section.
   */
  #instrumentSection(collection) {
    const elements = this.#elements;
    const moving = collection[InstrumentCollectionKey.INSTRUMENTS].filter((instrument) => instrument[InstrumentKey.JOINTS].length);
    const instrument = elements.select(moving.map((entry) => entry[InstrumentKey.IDENTIFIER]));
    const send = (pose) => this.command(LaboratoryRoute.INSTRUMENT, { [InstrumentRequestKey.INSTRUMENT]: instrument.value, [InstrumentRequestKey.POSE]: pose });
    return this.#section(
      Text.INSTRUMENT_COLLECTION,
      elements.row(instrument, elements.button(Text.INSPECT, () => send(InstrumentPose.INSPECTION)), elements.button(Text.REST, () => send(InstrumentPose.REST))),
    );
  }
}
