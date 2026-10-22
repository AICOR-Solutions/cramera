/**
 * A live publisher's routes as the browser calls them.
 */

import { LiveRoute } from '../protocol.js';
import { ViewerApi } from '../core/viewer-api.js';

// %% client

export class LiveClient {
  /**
   * The publisher's routes, resolved against its address.
   * @type {ViewerApi}
   */
  #api;

  /**
   * @param {function(string, Object=): Promise<Response>} fetch Fetches a URL.
   * @param {string} address The publisher's address, such as `http://127.0.0.1:8765/`.
   */
  constructor(fetch, address) {
    this.#api = new ViewerApi(fetch, address.endsWith('/') ? address : `${address}/`);
  }

  /**
   * @param {string} route A `LiveRoute` value.
   * @param {AbortSignal=} signal Cancels the request.
   * @returns {Promise<Object>} The publisher's answer to a read.
   */
  read(route, signal) {
    return this.#api.json(this.#api.url(route), signal);
  }

  /**
   * @param {string} route A `LiveRoute` value.
   * @param {Object=} body The request document, empty for an action without one.
   * @returns {Promise<Object>} The publisher's answer.
   */
  send(route, body = {}) {
    return this.#api.postJson(this.#api.url(route), body);
  }

  /**
   * @param {Object} request A recording save request.
   * @returns {Promise<Object>} The saved scene.
   */
  saveRecording(request) {
    return this.send(LiveRoute.RECORDING_SAVE, request);
  }
}
