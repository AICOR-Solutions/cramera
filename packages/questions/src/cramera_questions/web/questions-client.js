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
   * Whether new queries can be answered: always, by the plugin's routes.
   * @type {boolean}
   */
  readOnly = false;

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
   * @param {number|null} frame The frame of the recording shown, which a question
   *   about the paused world is asked at.
   * @returns {Promise<Object>} The answer.
   */
  query(scene, code, scope, frame = null) {
    const body = { [QueryRequestKey.SCENE]: scene, [QueryRequestKey.CODE]: code, [QueryRequestKey.SCOPE]: scope };
    if (frame !== null) body[QueryRequestKey.FRAME] = frame;
    return this.#api.postJson(this.#url(QuestionsRoute.QUERY), body);
  }

  /**
   * @param {string} scene A bundle name.
   * @param {string} scope A `QueryScope` value.
   * @returns {Promise<Array<Object>>} The names a query of that scope may use.
   */
  async vocabulary(scene, scope) {
    const answer = await this.#api.json(this.#url(QuestionsRoute.VOCABULARY, { [QuestionsParameter.SCENE]: scene, [QuestionsParameter.SCOPE]: scope }));
    return answer.entries ?? [];
  }

  /**
   * @param {string} scene A bundle name.
   * @param {string} scope A `QueryScope` value.
   * @param {string} name A variable's or class's name.
   * @returns {Promise<Array<Object>>} The members that may follow the name's dot.
   */
  async members(scene, scope, name) {
    const answer = await this.#api.json(this.#url(QuestionsRoute.MEMBERS, { [QuestionsParameter.SCENE]: scene, [QuestionsParameter.SCOPE]: scope, [QuestionsParameter.NAME]: name }));
    return answer.members ?? answer.entries ?? [];
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
