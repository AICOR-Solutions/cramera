/**
 * A connection to a live publisher: polls its information, state, plan, statechart
 * and recording, keeps only the newest answers, and reports them to the application.
 */

import { Capability, LiveInfoKey, LiveRoute, LiveSceneKey, LiveStateKey, ViewerEvent } from '../protocol.js';

/**
 * How often each part of the publisher is polled, in milliseconds.
 */
export const PollInterval = Object.freeze({ INFO: 1000, STATE: 100, PLAN: 500, RECORDING: 1000 });

// %% callbacks

/**
 * What a session reports to.
 */
export class LiveListener {
  /**
   * @param {function(string): void} showScene Shows the bundle of the publisher's world.
   * @param {function(Object): void} showState Applies a new world state.
   * @param {function(Object): void} showPlan Shows the executing plan.
   * @param {function(Object): void} showStatechart Shows the ticked statechart.
   * @param {function(Object): void} showRecording Shows the recording's status.
   */
  constructor(showScene, showState, showPlan, showStatechart, showRecording) {
    /**
     * Shows the bundle of the publisher's world.
     * @type {function(string): void}
     */
    this.showScene = showScene;
    /**
     * Applies a new world state.
     * @type {function(Object): void}
     */
    this.showState = showState;
    /**
     * Shows the executing plan.
     * @type {function(Object): void}
     */
    this.showPlan = showPlan;
    /**
     * Shows the ticked statechart.
     * @type {function(Object): void}
     */
    this.showStatechart = showStatechart;
    /**
     * Shows the recording's status.
     * @type {function(Object): void}
     */
    this.showRecording = showRecording;
  }
}

// %% session

export class LiveSession {
  /**
   * The publisher's routes.
   * @type {import('./live-client.js').LiveClient}
   */
  client;

  /**
   * Starts and stops timers; `window` in the browser.
   * @type {{setInterval: Function, clearInterval: Function}}
   */
  #timers;

  /**
   * The bus connection changes are published on.
   * @type {import('../core/event-bus.js').EventBus}
   */
  #bus;

  /**
   * What the session reports to.
   * @type {LiveListener}
   */
  #listener;

  /**
   * The running timers.
   * @type {Array<number>}
   */
  #intervals = [];

  /**
   * The publisher's last information, or null while it does not answer.
   * @type {Object|null}
   */
  info = null;

  /**
   * The bundle signature whose scene is shown.
   * @type {string|null}
   */
  #shownSignature = null;

  /**
   * The newest state applied.
   * @type {number}
   */
  #sequenceNumber = -1;

  /**
   * Whether the publisher's scene is shown, so states can be applied.
   * @type {boolean}
   */
  #sceneShown = false;

  /**
   * The requests in flight, by route, so a slow answer is not overtaken.
   * @type {Set<string>}
   */
  #pending = new Set();

  /**
   * @param {import('./live-client.js').LiveClient} client The publisher's routes.
   * @param {{setInterval: Function, clearInterval: Function}} timers Starts and stops timers.
   * @param {import('../core/event-bus.js').EventBus} bus The bus connection changes are published on.
   * @param {LiveListener} listener What the session reports to.
   */
  constructor(client, timers, bus, listener) {
    this.client = client;
    this.#timers = timers;
    this.#bus = bus;
    this.#listener = listener;
  }

  /**
   * Start polling.
   */
  start() {
    this.stop();
    this.#every(PollInterval.INFO, () => this.pollInfo());
    this.#every(PollInterval.STATE, () => this.pollState());
    this.#every(PollInterval.PLAN, () => this.pollPlan());
    this.#every(PollInterval.RECORDING, () => this.pollRecording());
    this.pollInfo();
  }

  /**
   * Stop polling.
   */
  stop() {
    for (const interval of this.#intervals) this.#timers.clearInterval(interval);
    this.#intervals = [];
    if (this.info) this.#bus.publish(ViewerEvent.LIVE_DISCONNECTED, null);
    this.info = null;
    this.#shownSignature = null;
    this.#sceneShown = false;
  }

  /**
   * @param {string} capability A `Capability` value.
   * @returns {boolean} Whether the connected publisher offers it.
   */
  offers(capability) {
    return (this.info?.[LiveInfoKey.CAPABILITIES] ?? []).includes(capability);
  }

  /**
   * Tell the session that the publisher's scene is shown, so states apply to it.
   */
  sceneShown() {
    this.#sceneShown = true;
    this.#sequenceNumber = -1;
  }

  /**
   * Read the publisher's information; when the world's model changed, have the
   * publisher bundle it unless it names its bundle already, and show that bundle.
   * @returns {Promise<void>} Settles once read or failed.
   */
  async pollInfo() {
    const info = await this.#once(LiveRoute.INFO);
    if (info === undefined) return;
    if (info === null) {
      if (this.info) this.#bus.publish(ViewerEvent.LIVE_DISCONNECTED, null);
      this.info = null;
      return;
    }
    if (!this.info) this.#bus.publish(ViewerEvent.LIVE_CONNECTED, info);
    this.info = info;
    const signature = info[LiveInfoKey.BUNDLE_SIGNATURE] ?? null;
    if (signature === this.#shownSignature) return;
    const scene = info[LiveInfoKey.SCENE] ?? (await this.#once(LiveRoute.LIVE_SCENE))?.[LiveSceneKey.SCENE];
    if (!scene) return;
    this.#shownSignature = signature;
    this.#sceneShown = false;
    this.#listener.showScene(scene);
  }

  /**
   * Read the world state and apply it when it is newer than the last one.
   * @returns {Promise<void>} Settles once read or failed.
   */
  async pollState() {
    if (!this.info || !this.#sceneShown) return;
    const state = await this.#once(LiveRoute.STATE);
    if (!state || state[LiveStateKey.SEQUENCE_NUMBER] <= this.#sequenceNumber) return;
    this.#sequenceNumber = state[LiveStateKey.SEQUENCE_NUMBER];
    this.#listener.showState(state);
  }

  /**
   * Read the plan and the statechart when the publisher offers them.
   * @returns {Promise<void>} Settles once read or failed.
   */
  async pollPlan() {
    if (!this.info) return;
    const [plan, chart] = await Promise.all([
      this.offers(Capability.PLAN) ? this.#once(LiveRoute.PLAN) : null,
      this.offers(Capability.STATECHART) ? this.#once(LiveRoute.STATECHART) : null,
    ]);
    if (plan) this.#listener.showPlan(plan);
    if (chart) this.#listener.showStatechart(chart);
  }

  /**
   * Read the recording's status when the publisher records.
   * @returns {Promise<void>} Settles once read or failed.
   */
  async pollRecording() {
    if (!this.info || !this.offers(Capability.RECORDING)) return;
    const status = await this.#once(LiveRoute.RECORDING);
    if (status) this.#listener.showRecording(status);
  }

  /**
   * @param {string} route A `LiveRoute` value.
   * @returns {Promise<Object|null|undefined>} The answer, null when the publisher did
   *   not answer, undefined when a request to the route is still in flight.
   */
  async #once(route) {
    if (this.#pending.has(route)) return undefined;
    this.#pending.add(route);
    const answer = await this.client.read(route).catch(() => null);
    this.#pending.delete(route);
    return answer;
  }

  /**
   * @param {number} milliseconds The interval.
   * @param {function(): void} poll The poll to repeat.
   */
  #every(milliseconds, poll) {
    this.#intervals.push(this.#timers.setInterval(poll, milliseconds));
  }
}
