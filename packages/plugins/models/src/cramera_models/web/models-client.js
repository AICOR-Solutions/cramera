/**
 * The models plugin's routes as the Models panel calls them.
 */

import { RequestFailed } from '../../core/viewer-api.js';
import {
  ErrorKey,
  ModelRequestKey,
  ModelsRoute,
  ModelUploadKey,
  PluginName,
  ViewerRoute,
} from '../../protocol.js';

/**
 * The media type of the JSON bodies the routes read and answer.
 */
const JSON_MEDIA_TYPE = 'application/json';

/**
 * The request header naming a body's media type.
 */
const CONTENT_TYPE = 'Content-Type';

/**
 * The method of the routes that read a body.
 */
const POST = 'POST';

// %% client

export class ModelsClient {
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
   * @returns {Promise<Object>} The workbench state: whether a model is loaded, and its variables.
   * @throws {RequestFailed} When the workbench cannot answer, for example without its libraries.
   */
  state() {
    return this.#answer(this.#url(ModelsRoute.STATE));
  }

  /**
   * @param {string} name The model file's name.
   * @param {string} text The model file's text.
   * @returns {Promise<Object>} The workbench state with the loaded model.
   */
  load(name, text) {
    return this.#post(ModelsRoute.LOAD, { [ModelUploadKey.NAME]: name, [ModelUploadKey.TEXT]: text });
  }

  /**
   * @param {Array<Object>} query The constraints of the query event.
   * @param {Array<Object>} evidence The constraints of the evidence event.
   * @returns {Promise<Object>} The probability answer.
   */
  probability(query, evidence) {
    return this.#post(ModelsRoute.PROBABILITY, { [ModelRequestKey.QUERY]: query, [ModelRequestKey.EVIDENCE]: evidence });
  }

  /**
   * @param {Array<string>} variables The variables whose posterior marginals are asked for.
   * @param {Array<Object>} evidence The constraints of the evidence event.
   * @returns {Promise<Object>} The posterior answer with one Plotly figure per variable.
   */
  posterior(variables, evidence) {
    return this.#post(ModelsRoute.POSTERIOR, { [ModelRequestKey.VARIABLES]: variables, [ModelRequestKey.EVIDENCE]: evidence });
  }

  /**
   * @param {Array<Object>} evidence The constraints of the evidence event.
   * @returns {Promise<Object>} The mode answer.
   */
  mode(evidence) {
    return this.#post(ModelsRoute.MODE, { [ModelRequestKey.EVIDENCE]: evidence });
  }

  /**
   * @param {string} route A `ModelsRoute` value.
   * @param {Object} body The request document.
   * @returns {Promise<Object>} The decoded answer.
   */
  #post(route, body) {
    return this.#answer(this.#url(route), {
      method: POST,
      headers: { [CONTENT_TYPE]: JSON_MEDIA_TYPE },
      body: JSON.stringify(body),
    });
  }

  /**
   * @param {string} url A route's URL.
   * @param {Object=} init The request's method, headers and body.
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

  /**
   * @param {string} route A `ModelsRoute` value.
   * @returns {string} The route's URL below the page's base.
   */
  #url(route) {
    return this.#api.url(`${ViewerRoute.PLUGIN_API}${PluginName.MODELS}/${route}`);
  }
}
