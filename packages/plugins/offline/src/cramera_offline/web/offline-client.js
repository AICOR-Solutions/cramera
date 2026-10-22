/**
 * The offline plugin's routes as the tour reads them.
 */

import { ErrorKey, OfflineParameter, OfflineRoute, PluginName, ViewerRoute } from '../../protocol.js';

/**
 * The HTTP status of a route that has nothing to answer.
 */
const NOT_FOUND = 404;

// %% answers

/**
 * The storyboard, or why there is none.
 */
export class StoryboardAnswer {
  /**
   * @param {Object|null} storyboard The storyboard, or null.
   * @param {string|null} problem Why a storyboard exists but cannot be read, or null.
   */
  constructor(storyboard, problem) {
    /**
     * The storyboard, or null.
     * @type {Object|null}
     */
    this.storyboard = storyboard;
    /**
     * Why a storyboard exists but cannot be read, or null.
     * @type {string|null}
     */
    this.problem = problem;
  }
}

// %% client

export class OfflineClient {
  /**
   * Fetches a URL; `window.fetch` in the browser.
   * @type {function(string): Promise<Response>}
   */
  #fetch;

  /**
   * The viewer's routes, for their URLs.
   * @type {import('../../core/viewer-api.js').ViewerApi}
   */
  #api;

  /**
   * @param {function(string): Promise<Response>} fetch Fetches a URL.
   * @param {import('../../core/viewer-api.js').ViewerApi} api The viewer's routes.
   */
  constructor(fetch, api) {
    this.#fetch = fetch;
    this.#api = api;
  }

  /**
   * @returns {Promise<StoryboardAnswer>} The storyboard; none without a storyboard
   *   file, and the reason when the file cannot be read.
   */
  async storyboard() {
    const answer = await this.#fetch(this.#url(OfflineRoute.STORYBOARD));
    if (answer.ok) return new StoryboardAnswer(await answer.json(), null);
    if (answer.status === NOT_FOUND) return new StoryboardAnswer(null, null);
    return new StoryboardAnswer(null, (await answer.json())[ErrorKey.ERROR]);
  }

  /**
   * @param {string} scene A bundle name.
   * @returns {Promise<Object|null>} The bundle's completeness report, or null where
   *   the route is not served, as on a static site.
   */
  async bundleCheck(scene) {
    const query = new URLSearchParams({ [OfflineParameter.SCENE]: scene });
    const answer = await this.#fetch(`${this.#url(OfflineRoute.BUNDLE_CHECK)}?${query}`);
    return answer.ok ? answer.json() : null;
  }

  /**
   * @param {string} route An `OfflineRoute` value.
   * @returns {string} The route's URL below the page's base.
   */
  #url(route) {
    return this.#api.url(`${ViewerRoute.PLUGIN_API}${PluginName.OFFLINE}/${route}`);
  }
}
