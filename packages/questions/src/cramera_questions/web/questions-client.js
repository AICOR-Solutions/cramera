/**
 * The questions plugin's routes as the browser calls them.
 */

import {
  PluginName,
  QueryRequestKey,
  QuestionRequestKey,
  QuestionsParameter,
  QuestionsRoute,
  ViewerRoute,
} from '../../protocol.js';

// %% client

export class QuestionsClient {
  /**
   * The viewer's routes.
   * @type {import('../../core/viewer-api.js').ViewerApi}
   */
  #api;

  /**
   * @param {import('../../core/viewer-api.js').ViewerApi} api The viewer's routes.
   */
  constructor(api) {
    this.#api = api;
  }

  /**
   * @param {string} scene A bundle name.
   * @param {AbortSignal=} signal Cancels the request when another scene is shown.
   * @returns {Promise<Object>} The scene's preset catalog.
   */
  presets(scene, signal) {
    return this.#api.json(this.#url(QuestionsRoute.PRESETS, { [QuestionsParameter.SCENE]: scene }), signal);
  }

  /**
   * @param {string} scene A bundle name.
   * @param {string} view A `GraphViewName` value.
   * @param {AbortSignal=} signal Cancels the request when another view is chosen.
   * @returns {Promise<Object>} The graph view.
   */
  graph(scene, view, signal) {
    return this.#api.json(this.#url(QuestionsRoute.GRAPH, { [QuestionsParameter.SCENE]: scene, [QuestionsParameter.VIEW]: view }), signal);
  }

  /**
   * @param {string} scene A bundle name.
   * @param {string} code A query in the entity query language.
   * @param {string} scope The `QueryScope` the query ranges over.
   * @returns {Promise<Object>} The answer.
   */
  query(scene, code, scope) {
    const body = { [QueryRequestKey.SCENE]: scene, [QueryRequestKey.CODE]: code, [QueryRequestKey.SCOPE]: scope };
    return this.#api.postJson(this.#url(QuestionsRoute.QUERY), body);
  }

  /**
   * @param {string} scene A bundle name.
   * @param {string} text A question in plain language.
   * @returns {Promise<Object>} The matched preset, or why none matched.
   */
  question(scene, text) {
    const body = { [QuestionRequestKey.SCENE]: scene, [QuestionRequestKey.TEXT]: text };
    return this.#api.postJson(this.#url(QuestionsRoute.QUESTION), body);
  }

  /**
   * @param {string} route A `QuestionsRoute` value.
   * @param {Object<string, string>=} parameters Query parameters.
   * @returns {string} The route's URL.
   */
  #url(route, parameters = {}) {
    const url = new URL(this.#api.url(`${ViewerRoute.PLUGIN_API}${PluginName.QUESTIONS}/${route}`));
    for (const [name, value] of Object.entries(parameters)) url.searchParams.set(name, value);
    return url.href;
  }
}
