/**
 * The cable lab plugin's routes as the cable lab page calls them.
 */

import { RequestFailed } from '../../../core/viewer-api.js';
import { CableLabRoute, ErrorKey, PluginName, ViewerRoute } from '../../../protocol.js';

/**
 * The media type of the JSON bodies the routes read and answer.
 */
const JSON_MEDIA_TYPE = 'application/json';

/**
 * The request header naming a body's media type.
 */
const CONTENT_TYPE = 'Content-Type';

/**
 * The method of the routes that change the lab.
 */
const POST = 'POST';

/**
 * How the requests are cached: never, the state changes all the time.
 */
const NO_STORE = 'no-store';

// %% client

export class CableLabClient {
  /**
   * Fetches a URL; `window.fetch` in the browser.
   * @type {function(string, Object=): Promise<Response>}
   */
  #fetch;

  /**
   * The viewer's address, ending in `/`.
   * @type {string}
   */
  #viewer;

  /**
   * @param {function(string, Object=): Promise<Response>} fetch Fetches a URL.
   * @param {string} viewer The viewer's address, ending in `/`.
   */
  constructor(fetch, viewer) {
    this.#fetch = fetch;
    this.#viewer = viewer;
  }

  /**
   * @returns {Promise<Object>} The lifecycle and the measured cable.
   */
  state() {
    return this.#answer(CableLabRoute.STATE, { cache: NO_STORE });
  }

  /**
   * @param {Object} configuration A cable configuration document.
   * @returns {Promise<Object>} The state of the new simulation.
   */
  start(configuration) {
    return this.#post(CableLabRoute.START, configuration);
  }

  /**
   * @param {Object} command A gripper command document.
   * @returns {Promise<Object>} The state after the command.
   */
  command(command) {
    return this.#post(CableLabRoute.COMMAND, command);
  }

  /**
   * @returns {Promise<Object>} The state of the rebuilt simulation.
   */
  reset() {
    return this.#post(CableLabRoute.RESET, {});
  }

  /**
   * @returns {Promise<Object>} The last state of the stopped simulation.
   */
  stop() {
    return this.#post(CableLabRoute.STOP, {});
  }

  /**
   * @param {string} route A `CableLabRoute` value.
   * @param {Object} body The request document.
   * @returns {Promise<Object>} The decoded answer.
   */
  #post(route, body) {
    return this.#answer(route, {
      method: POST,
      cache: NO_STORE,
      headers: { [CONTENT_TYPE]: JSON_MEDIA_TYPE },
      body: JSON.stringify(body),
    });
  }

  /**
   * @param {string} route A `CableLabRoute` value.
   * @param {Object} init The request's method, headers and body.
   * @returns {Promise<Object>} The decoded answer.
   * @throws {RequestFailed} When the answer has an error status.
   */
  async #answer(route, init) {
    const url = new URL(`${ViewerRoute.PLUGIN_API}${PluginName.CABLE_LAB}/${route}`.replace(/^\//, ''), this.#viewer).href;
    const answer = await this.#fetch(url, init);
    if (answer.ok) return answer.json();
    const explained = (answer.headers.get(CONTENT_TYPE) ?? '').startsWith(JSON_MEDIA_TYPE);
    const reason = explained ? (await answer.json())[ErrorKey.ERROR] : answer.statusText;
    throw new RequestFailed(url, answer.status, reason);
  }
}
