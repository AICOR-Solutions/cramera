/**
 * The workshop plugin's routes as the Workshop panel calls them.
 */

import { RequestFailed } from '../../core/viewer-api.js';
import { ErrorKey, PluginName, ViewerRoute, WorkshopRoute } from '../../protocol.js';

/**
 * The media type of the JSON bodies the routes read and answer.
 */
const JSON_MEDIA_TYPE = 'application/json';

/**
 * The request header naming a body's media type.
 */
const CONTENT_TYPE = 'Content-Type';

/**
 * The method of the command route.
 */
const POST = 'POST';

/**
 * How the requests are cached: never, the state changes all the time.
 */
const NO_STORE = 'no-store';

// %% client

export class WorkshopClient {
  /**
   * Fetches a URL; `window.fetch` in the browser.
   * @type {function(string, Object=): Promise<Response>}
   */
  #fetch;

  /**
   * The viewer's routes, for their URLs.
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
   * @returns {Promise<Object>} The measured state of the contact world.
   * @throws {RequestFailed} When the viewer refuses the request.
   */
  state() {
    return this.#answer(this.#url(WorkshopRoute.STATE), { cache: NO_STORE });
  }

  /**
   * @param {Object} command A workshop command document.
   * @returns {Promise<Object>} The state after the command.
   * @throws {RequestFailed} When the workshop refuses the command.
   */
  command(command) {
    return this.#answer(this.#url(WorkshopRoute.COMMAND), {
      method: POST,
      cache: NO_STORE,
      headers: { [CONTENT_TYPE]: JSON_MEDIA_TYPE },
      body: JSON.stringify(command),
    });
  }

  /**
   * @param {string} route A `WorkshopRoute` value.
   * @returns {string} The route's URL.
   */
  #url(route) {
    return this.#api.url(`${ViewerRoute.PLUGIN_API}${PluginName.WORKSHOP}/${route}`);
  }

  /**
   * @param {string} url A route's URL.
   * @param {Object} init The request's method, headers and body.
   * @returns {Promise<Object>} The decoded answer.
   * @throws {RequestFailed} When the answer has an error status.
   */
  async #answer(url, init) {
    const answer = await this.#fetch(url, init);
    if (answer.ok) return answer.json();
    const explained = (answer.headers.get(CONTENT_TYPE) ?? '').startsWith(JSON_MEDIA_TYPE);
    const reason = explained ? (await answer.json())[ErrorKey.ERROR] : answer.statusText;
    throw new RequestFailed(url, answer.status, reason);
  }
}
