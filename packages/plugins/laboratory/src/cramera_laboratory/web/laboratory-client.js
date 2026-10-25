/**
 * The laboratory's routes as the browser calls them: the shipped laboratories, the
 * device catalog and the contact simulation.
 */

import { RequestFailed } from '../../core/viewer-api.js';
import { ErrorKey, LaboratoryName, LaboratoryRoute, ViewerRoute } from '../../protocol.js';

/**
 * The media type of the JSON bodies the routes take and answer.
 */
const JSON_MEDIA_TYPE = 'application/json';

/**
 * The HTTP method of the routes that change something.
 */
const POST = 'POST';

// %% client

export class LaboratoryClient {
  /**
   * Fetches a URL; `window.fetch` in the browser.
   * @type {function(string, Object=): Promise<Response>}
   */
  #fetch;

  /**
   * The viewer's routes.
   * @type {import('../../core/viewer-api.js').ViewerApi}
   */
  #api;

  /**
   * @param {function(string, Object=): Promise<Response>} fetch Fetches a URL.
   * @param {import('../../core/viewer-api.js').ViewerApi} api The viewer's routes.
   */
  constructor(fetch, api) {
    this.#fetch = fetch;
    this.#api = api;
  }

  /**
   * @param {string} route A route of the laboratory.
   * @returns {string} The route's URL.
   */
  url(route) {
    return this.#api.url(`${ViewerRoute.PLUGIN_API}${LaboratoryName.PLUGIN}/${route}`);
  }

  /**
   * @returns {Promise<Object>} The shipped laboratories and whether the simulation can run.
   */
  laboratories() {
    return this.#api.json(this.url(LaboratoryRoute.LABORATORIES));
  }

  /**
   * @returns {Promise<Object>} The device catalog.
   */
  devices() {
    return this.#api.json(this.url(LaboratoryRoute.DEVICES));
  }

  /**
   * @param {string} device A device's folder name.
   * @param {string} file A file of the folder.
   * @returns {string} The file's URL.
   */
  deviceFileUrl(device, file) {
    return this.url(`${LaboratoryRoute.DEVICE_FILES}${encodeURIComponent(device)}/${file}`);
  }

  /**
   * @returns {Promise<Object>} The PR2 vessel transfer demo's state.
   */
  transfer() {
    return this.#api.json(this.url(LaboratoryRoute.TRANSFER_STATE));
  }

  /**
   * @returns {Promise<Object>} The simulation's state.
   */
  state() {
    return this.#api.json(this.url(LaboratoryRoute.STATE));
  }

  /**
   * Send a command.
   * @param {string} route A route of the laboratory.
   * @param {Object=} body The request document; an empty object by default.
   * @returns {Promise<Object>} The answer.
   * @throws {RequestFailed} When the laboratory refuses the command.
   */
  async send(route, body = {}) {
    const url = this.url(route);
    const answer = await this.#fetch(url, {
      method: POST,
      headers: { 'Content-Type': JSON_MEDIA_TYPE },
      body: JSON.stringify(body),
    });
    const decoded = await answer.json();
    if (!answer.ok) throw new RequestFailed(url, answer.status, decoded[ErrorKey.ERROR] ?? answer.statusText);
    return decoded;
  }
}
