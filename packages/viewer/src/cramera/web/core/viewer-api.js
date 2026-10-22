/**
 * The viewer's HTTP routes as the browser application calls them.
 */

import { ErrorKey, ViewerRoute } from '../protocol.js';

/**
 * The media type of JSON answers, which explain errors.
 */
const JSON_MEDIA_TYPE = 'application/json';

// %% errors

/**
 * A request the viewer answered with an error status.
 */
export class RequestFailed extends Error {
  /**
   * @param {string} url The requested URL.
   * @param {number} status The answer's HTTP status.
   * @param {string} reason The reason the viewer gave, or the status text.
   */
  constructor(url, status, reason) {
    super(`${url}: ${reason}`);
    /**
     * The requested URL.
     * @type {string}
     */
    this.url = url;
    /**
     * The answer's HTTP status.
     * @type {number}
     */
    this.status = status;
    /**
     * The reason the viewer gave.
     * @type {string}
     */
    this.reason = reason;
  }
}

// %% client

export class ViewerApi {
  /**
   * Fetches a URL; `window.fetch` in the browser.
   * @type {function(string, Object=): Promise<Response>}
   */
  #fetch;

  /**
   * The URL the routes are relative to.
   * @type {string}
   */
  #base;

  /**
   * @param {function(string, Object=): Promise<Response>} fetch Fetches a URL.
   * @param {string} base The URL the routes are relative to, ending in `/`.
   */
  constructor(fetch, base) {
    this.#fetch = fetch;
    this.#base = base;
  }

  /**
   * @returns {Promise<Object>} The viewer's information.
   */
  info() {
    return this.json(this.url(ViewerRoute.INFO));
  }

  /**
   * @returns {Promise<Object>} The merged scenes index.
   */
  scenes() {
    return this.json(this.url(ViewerRoute.SCENES));
  }

  /**
   * @param {string} scene A bundle name.
   * @param {string} file A file of the bundle.
   * @returns {string} The URL of the bundle file.
   */
  sceneFileUrl(scene, file) {
    return this.url(`${ViewerRoute.SCENE_FILES}${encodeURIComponent(scene)}/${file}`);
  }

  /**
   * @param {string} scene A bundle name.
   * @param {string} file A JSON file of the bundle.
   * @param {AbortSignal=} signal Cancels the request when a newer one replaces it.
   * @returns {Promise<Object>} The decoded file.
   */
  sceneJson(scene, file, signal) {
    return this.json(this.sceneFileUrl(scene, file), signal);
  }

  /**
   * @param {string} route A route path starting with `/`.
   * @returns {string} The route's URL.
   */
  url(route) {
    return new URL(route.replace(/^\//, ''), this.#base).href;
  }

  /**
   * @param {string} url A URL answering JSON.
   * @param {AbortSignal=} signal Cancels the request.
   * @returns {Promise<Object>} The decoded answer.
   * @throws {RequestFailed} When the answer has an error status.
   */
  async json(url, signal) {
    const answer = await this.#fetch(url, { signal });
    if (answer.ok) return answer.json();
    const explained = (answer.headers.get('Content-Type') ?? '').startsWith(JSON_MEDIA_TYPE);
    const reason = explained ? (await answer.json())[ErrorKey.ERROR] : answer.statusText;
    throw new RequestFailed(url, answer.status, reason);
  }
}
