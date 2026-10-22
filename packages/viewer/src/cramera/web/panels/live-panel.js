/**
 * The Live panel: connect to a running CRAM process, see what it offers, and stop,
 * save or discard its recording.
 */

import {
  Capability,
  LiveInfoKey,
  RecordingSaveRequestKey,
  RecordingState,
  RecordingStatusKey,
  SavedSceneKey,
  SceneDestination,
} from '../protocol.js';
import { SidePanel } from './panel-host.js';

/**
 * The address a live publisher listens on unless told otherwise.
 */
export const DEFAULT_LIVE_ADDRESS = 'http://127.0.0.1:8765';

// %% actions

/**
 * What the panel's controls do.
 */
export class LiveActions {
  /**
   * @param {function(string): void} connect Connects to a publisher address.
   * @param {function(): void} disconnect Ends the connection.
   * @param {function(): Promise<Object>} stopRecording Ends the recording.
   * @param {function(Object): Promise<Object>} saveRecording Saves the ended recording.
   * @param {function(): Promise<Object>} discardRecording Throws the ended recording away.
   */
  constructor(connect, disconnect, stopRecording, saveRecording, discardRecording) {
    /**
     * Connects to a publisher address.
     * @type {function(string): void}
     */
    this.connect = connect;
    /**
     * Ends the connection.
     * @type {function(): void}
     */
    this.disconnect = disconnect;
    /**
     * Ends the recording.
     * @type {function(): Promise<Object>}
     */
    this.stopRecording = stopRecording;
    /**
     * Saves the ended recording.
     * @type {function(Object): Promise<Object>}
     */
    this.saveRecording = saveRecording;
    /**
     * Throws the ended recording away.
     * @type {function(): Promise<Object>}
     */
    this.discardRecording = discardRecording;
  }
}

// %% panel

export class LivePanel {
  /**
   * The panel.
   * @type {SidePanel}
   */
  panel;

  /**
   * What the controls do.
   * @type {LiveActions}
   */
  #actions;

  /**
   * The publisher's address.
   * @type {HTMLInputElement}
   */
  #address;

  /**
   * Connects or disconnects.
   * @type {HTMLButtonElement}
   */
  #connection;

  /**
   * The connection's state.
   * @type {HTMLElement}
   */
  #state;

  /**
   * The recording's controls.
   * @type {HTMLElement}
   */
  #recording;

  /**
   * The outcome of the last save, kept while the recording's controls change.
   * @type {HTMLElement}
   */
  #notice;

  /**
   * Whether a connection is wanted.
   * @type {boolean}
   */
  #connecting = false;

  /**
   * @param {Document} document The page.
   * @param {LiveActions} actions What the controls do.
   */
  constructor(document, actions) {
    this.#actions = actions;
    this.panel = new SidePanel('live', 'Live', document.createElement('section'));
    this.panel.element.classList.add('live');
    const form = document.createElement('form');
    form.className = 'connect';
    this.#address = document.createElement('input');
    this.#address.type = 'url';
    this.#address.value = DEFAULT_LIVE_ADDRESS;
    this.#address.setAttribute('aria-label', 'Live publisher address');
    this.#connection = document.createElement('button');
    form.append(this.#address, this.#connection);
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      if (this.#connecting) this.#actions.disconnect();
      else this.#actions.connect(this.#address.value);
    });
    this.#state = document.createElement('p');
    this.#state.className = 'live-state';
    this.#recording = document.createElement('div');
    this.#recording.className = 'recording';
    this.#notice = document.createElement('p');
    this.#notice.className = 'notice';
    this.panel.element.append(form, this.#state, this.#recording, this.#notice);
    this.showConnecting(false, null);
  }

  /**
   * @param {boolean} connecting Whether a connection is wanted.
   * @param {Object|null} info The publisher's information, or null while it does not answer.
   * @param {string=} address The address connected to.
   */
  showConnecting(connecting, info, address) {
    this.#connecting = connecting;
    if (address) this.#address.value = address;
    this.#connection.textContent = connecting ? 'Disconnect' : 'Connect';
    this.#address.disabled = connecting;
    if (!connecting) this.#state.textContent = 'Not connected. Start a demo with cramera-live, then connect.';
    else if (!info) this.#state.textContent = 'Waiting for the publisher to answer…';
    else this.#state.textContent = `Connected to ${info[LiveInfoKey.PUBLISHER]}; it offers ${(info[LiveInfoKey.CAPABILITIES] ?? []).join(', ') || 'nothing'}.`;
    this.panel.element.dataset.connected = String(Boolean(connecting && info));
    if (!info || !(info[LiveInfoKey.CAPABILITIES] ?? []).includes(Capability.RECORDING)) this.#recording.replaceChildren();
  }

  /**
   * @param {Object} status The recording's status.
   */
  showRecording(status) {
    const document = this.panel.element.ownerDocument;
    const state = status[RecordingStatusKey.STATE];
    const summary = document.createElement('p');
    summary.textContent = `Recording: ${state}, ${status[RecordingStatusKey.FRAME_COUNT] ?? 0} frames, ${(status[RecordingStatusKey.DURATION_SECONDS] ?? 0).toFixed(1)} s`;
    const controls = [summary];
    if (state === RecordingState.RECORDING) controls.push(this.#button('Stop recording', () => this.#actions.stopRecording()));
    if (state === RecordingState.FINALIZED) controls.push(this.#saveForm(), this.#button('Discard', () => this.#actions.discardRecording()));
    this.#recording.replaceChildren(...controls);
  }

  /**
   * @returns {HTMLElement} The form saving the ended recording under a name.
   */
  #saveForm() {
    const document = this.panel.element.ownerDocument;
    const form = document.createElement('form');
    form.className = 'save';
    const name = document.createElement('input');
    name.placeholder = 'scene_name';
    name.setAttribute('aria-label', 'Scene name');
    const destination = document.createElement('select');
    destination.setAttribute('aria-label', 'Save to');
    for (const value of Object.values(SceneDestination)) {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = value;
      destination.append(option);
    }
    const save = document.createElement('button');
    save.textContent = 'Save';
    form.append(name, destination, save);
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const request = { [RecordingSaveRequestKey.NAME]: name.value, [RecordingSaveRequestKey.DESTINATION]: destination.value };
      this.#actions.saveRecording(request).then(
        (saved) => { this.#notice.textContent = `Saved as ${saved[SavedSceneKey.SCENE]}; choose it in the scene picker.`; },
        (error) => { this.#notice.textContent = error.message; },
      );
    });
    return form;
  }

  /**
   * @param {string} text The button's text.
   * @param {function(): void} action What it does.
   * @returns {HTMLButtonElement} The button.
   */
  #button(text, action) {
    const button = this.panel.element.ownerDocument.createElement('button');
    button.type = 'button';
    button.textContent = text;
    button.addEventListener('click', action);
    return button;
  }
}
