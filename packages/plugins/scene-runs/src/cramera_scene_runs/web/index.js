/**
 * The Runs panel: start one of the runs the server offers, one at a time, follow it
 * live, stop it, and replay its recording.
 */

import {
  SceneRunKey,
  SceneRunsName,
  SceneRunsRoute,
  SceneRunsStateKey,
  SceneRunState,
  SceneRunStatusKey,
  ViewerEvent,
  ViewerRoute,
} from '../../protocol.js';
import { LIVE_PARAMETER, withScene } from '../../core/scene-address.js';
import { SidePanel } from '../../panels/panel-host.js';

/**
 * The panel's tab text.
 */
export const PANEL_TITLE = 'Runs';

/**
 * How often the panel reads the runs' state, in milliseconds.
 */
export const POLL_INTERVAL = 2000;

// %% words

/**
 * @param {Object|null} status The run started last, or null.
 * @param {Array<Object>} runs The runs offered.
 * @returns {string} How far that run is, in a sentence.
 */
export function stateText(status, runs) {
  if (!status) return runs.length ? 'No run started yet.' : 'This viewer offers no runs.';
  const run = runs.find((offered) => offered[SceneRunKey.IDENTIFIER] === status[SceneRunStatusKey.IDENTIFIER]);
  const label = run?.[SceneRunKey.LABEL] ?? status[SceneRunStatusKey.IDENTIFIER];
  const state = status[SceneRunStatusKey.STATE];
  if (state === SceneRunState.RUNNING) return `${label} runs; its queries wait for Next in the Queries tab.`;
  if (state === SceneRunState.RECORDED) return `${label} was recorded as ${status[SceneRunStatusKey.RECORDING]}.`;
  if (state === SceneRunState.STOPPED) return `${label} was stopped.`;
  return `${label} failed:`;
}

/**
 * @param {string} href The address of the page.
 * @param {string} scene A recording.
 * @returns {URL} The page replaying the recording instead of following a live run.
 */
export function replayAddress(href, scene) {
  const url = withScene(href, scene);
  url.searchParams.delete(LIVE_PARAMETER);
  return url;
}

// %% panel

export class SceneRunsPanel {
  /**
   * The panel's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * The viewer's routes.
   * @type {import('../../core/viewer-api.js').ViewerApi}
   */
  #api;

  /**
   * The application's event bus.
   * @type {import('../../core/event-bus.js').EventBus}
   */
  #bus;

  /**
   * The page's address, which a replay changes.
   * @type {Location}
   */
  #location;

  /**
   * The offered runs.
   * @type {HTMLElement}
   */
  #runs;

  /**
   * How far the run started last is.
   * @type {HTMLElement}
   */
  #status;

  /**
   * The controls of the run started last and the end of its output.
   * @type {HTMLElement}
   */
  #controls;

  /**
   * Why the last request failed.
   * @type {HTMLElement}
   */
  #notice;

  /**
   * @param {Document} document The page.
   * @param {import('../../core/viewer-api.js').ViewerApi} api The viewer's routes.
   * @param {import('../../core/event-bus.js').EventBus} bus The application's event bus.
   * @param {Location} location The page's address.
   */
  constructor(document, api, bus, location) {
    this.#api = api;
    this.#bus = bus;
    this.#location = location;
    this.element = document.createElement('section');
    this.element.className = 'scene-runs';
    const intro = document.createElement('p');
    intro.textContent = 'Start a scene; one runs at a time, and the page follows it live.';
    this.#runs = document.createElement('ul');
    this.#runs.className = 'runs';
    this.#status = document.createElement('p');
    this.#status.className = 'run-state';
    this.#controls = document.createElement('div');
    this.#controls.className = 'run-controls';
    this.#notice = document.createElement('p');
    this.#notice.className = 'notice';
    this.element.append(intro, this.#runs, this.#status, this.#controls, this.#notice);
  }

  /**
   * Read the runs' state and show it.
   * @returns {Promise<void>} Settles once shown or failed.
   */
  async refresh() {
    await this.#request(() => this.#api.json(this.#url(SceneRunsRoute.STATE)));
  }

  /**
   * Start a run and have the page follow it.
   * @param {string} identifier The run.
   * @returns {Promise<void>} Settles once started or failed.
   */
  async start(identifier) {
    const started = await this.#request(() => this.#api.postJson(this.#url(`${SceneRunsRoute.START}${encodeURIComponent(identifier)}`), {}));
    if (started) this.#bus.publish(ViewerEvent.LIVE_REQUESTED, null);
  }

  /**
   * Stop the run that runs.
   * @returns {Promise<void>} Settles once stopped or failed.
   */
  async stop() {
    await this.#request(() => this.#api.postJson(this.#url(SceneRunsRoute.STOP), {}));
  }

  /**
   * Replay a recording in place of the live run.
   * @param {string} scene The recording.
   */
  replay(scene) {
    this.#location.assign(replayAddress(this.#location.href, scene).href);
  }

  /**
   * @param {Object} state The runs offered and the one started last.
   */
  show(state) {
    const document = this.element.ownerDocument;
    const runs = state[SceneRunsStateKey.RUNS] ?? [];
    const status = state[SceneRunsStateKey.CURRENT] ?? null;
    const running = status?.[SceneRunStatusKey.STATE] === SceneRunState.RUNNING;
    this.#runs.replaceChildren(...runs.map((run) => {
      const item = document.createElement('li');
      const label = document.createElement('strong');
      label.textContent = run[SceneRunKey.LABEL];
      const start = this.#button('Start', () => this.start(run[SceneRunKey.IDENTIFIER]));
      start.disabled = running;
      item.append(label, start);
      if (run[SceneRunKey.SCENE]) item.append(this.#button('Replay', () => this.replay(run[SceneRunKey.SCENE])));
      return item;
    }));
    this.#status.textContent = stateText(status, runs);
    const controls = [];
    if (running) controls.push(this.#button('Stop', () => this.stop()));
    if (status?.[SceneRunStatusKey.STATE] === SceneRunState.RECORDED) {
      controls.push(this.#button('Replay this run', () => this.replay(status[SceneRunStatusKey.RECORDING])));
    }
    if (status?.[SceneRunStatusKey.STATE] === SceneRunState.FAILED) {
      const log = document.createElement('pre');
      log.textContent = status[SceneRunStatusKey.LOG] ?? '';
      controls.push(log);
    }
    this.#controls.replaceChildren(...controls);
  }

  /**
   * @param {function(): Promise<Object>} send Sends a request answering the runs' state.
   * @returns {Promise<boolean>} Whether it was answered, and the answer shown.
   */
  async #request(send) {
    const state = await send().catch((error) => {
      this.#notice.textContent = error.message;
      return null;
    });
    if (!state) return false;
    this.#notice.textContent = '';
    this.show(state);
    return true;
  }

  /**
   * @param {string} route A route of the plugin.
   * @returns {string} Its URL.
   */
  #url(route) {
    return this.#api.url(`${ViewerRoute.PLUGIN_API}${SceneRunsName.PLUGIN}/${route}`);
  }

  /**
   * @param {string} text The button's text.
   * @param {function(): void} action What it does.
   * @returns {HTMLButtonElement} The button.
   */
  #button(text, action) {
    const button = this.element.ownerDocument.createElement('button');
    button.type = 'button';
    button.textContent = text;
    button.addEventListener('click', action);
    return button;
  }
}

// %% registration

/**
 * Add the Runs panel to the viewer and keep it up to date.
 * @param {import('../../app/plugin-modules.js').PluginContext} context What the viewer offers.
 * @param {Document=} document The viewer's document.
 * @param {{setInterval: function(function(): void, number): *}=} timers Repeats the reading.
 * @param {Location=} location The page's address.
 * @returns {SceneRunsPanel} The panel.
 */
export function register(context, document = globalThis.document, timers = globalThis, location = globalThis.location) {
  const panel = new SceneRunsPanel(document, context.api, context.bus, location);
  context.panels.add(new SidePanel(SceneRunsName.PLUGIN, PANEL_TITLE, panel.element));
  panel.refresh();
  timers.setInterval(() => panel.refresh(), POLL_INTERVAL);
  return panel;
}
