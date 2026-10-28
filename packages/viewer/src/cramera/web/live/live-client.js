/**
 * A live publisher's routes as the browser calls them.
 */

import { LiveParameter, LiveRoute } from '../protocol.js';
import { ViewerApi } from '../core/viewer-api.js';

/**
 * The address a live publisher listens on unless told otherwise.
 */
export const DEFAULT_LIVE_ADDRESS = 'http://127.0.0.1:8765';

/**
 * The names of this machine's loopback address, as a URL's host names them.
 */
const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);

// %% addresses

/**
 * A publisher answers pages of this machine's loopback names only, so a page opened at
 * another address, as a phone opens the viewer, reads the publisher at the default
 * address through the viewer, which relays what the page reads and nothing that
 * changes the run.
 * @param {string} page The address of the page.
 * @param {string} address A live publisher's address, as the page or the Live panel names it.
 * @param {string} relay The address of the viewer's relay of the publisher.
 * @returns {string} The address the page reads the publisher at.
 */
export function readAddressOf(page, address, relay) {
  if (LOOPBACK_HOSTS.has(new URL(page).hostname) || !URL.canParse(address)) return address;
  const publisher = new URL(address);
  const relayed = LOOPBACK_HOSTS.has(publisher.hostname) && publisher.port === new URL(DEFAULT_LIVE_ADDRESS).port;
  return relayed ? relay : address;
}

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
   * @param {number|null} revision The revision of the query steps shown, or null.
   * @returns {Promise<Object>} The query steps, or only their revision when the one
   *   named is the newest.
   */
  readQuerySteps(revision) {
    const route = this.#api.url(LiveRoute.QUERY_STEPS);
    return this.#api.json(revision === null ? route : `${route}?${LiveParameter.REVISION}=${revision}`);
  }

  /**
   * @param {string} key The key of an image a perception step took.
   * @returns {string} The image's URL.
   */
  perceptionImageUrl(key) {
    return `${this.#api.url(LiveRoute.PERCEPTION_IMAGE)}?${LiveParameter.KEY}=${encodeURIComponent(key)}`;
  }

  /**
   * @param {Object} request A recording save request.
   * @returns {Promise<Object>} The saved scene.
   */
  saveRecording(request) {
    return this.send(LiveRoute.RECORDING_SAVE, request);
  }
}
