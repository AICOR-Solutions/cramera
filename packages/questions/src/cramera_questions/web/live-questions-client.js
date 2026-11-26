/**
 * The live publisher's question routes as the browser calls them: queries asked of the
 * running process's own world, which the publisher holds still while it answers.
 */

import {
  LiveRoute,
  QueryRequestKey,
  QuestionRequestKey,
  QuestionsParameter,
} from '../../protocol.js';

// %% client

export class LiveQuestionsClient {
  /**
   * Whether new queries can be answered: always, by the running process.
   * @type {boolean}
   */
  readOnly = false;

  /**
   * Whether the answers are about the running process rather than a saved bundle.
   * @type {boolean}
   */
  live = true;

  /**
   * The publisher's routes.
   * @type {import('../../live/live-client.js').LiveClient}
   */
  #publisher;

  /**
   * Answers the graph views, which the publisher does not draw; null where none does.
   * @type {import('./questions-client.js').QuestionsClient|null}
   */
  #graphs;

  /**
   * @param {import('../../live/live-client.js').LiveClient} publisher The publisher's
   *   routes.
   * @param {import('./questions-client.js').QuestionsClient|null} graphs Answers the
   *   graph views of the bundle the publisher's world is shown as, or null.
   */
  constructor(publisher, graphs) {
    this.#publisher = publisher;
    this.#graphs = graphs;
  }

  /**
   * @param {string} scene A bundle name, unused: the publisher has one world.
   * @param {AbortSignal=} signal Cancels the request when another scene is shown.
   * @returns {Promise<Object>} The world's preset catalog.
   */
  presets(scene, signal) {
    return this.#publisher.read(LiveRoute.PRESETS, signal);
  }

  /**
   * @param {string} scene The bundle the publisher's world is shown as.
   * @param {string} view A `GraphViewName` value.
   * @param {AbortSignal=} signal Cancels the request when another view is chosen.
   * @returns {Promise<Object>} The graph view, drawn from the shown bundle.
   */
  graph(scene, view, signal) {
    if (!this.#graphs) return Promise.reject(new Error('The live publisher draws no graph views.'));
    return this.#graphs.graph(scene, view, signal);
  }

  /**
   * @param {string} scene The bundle the publisher's world is shown as.
   * @param {string} code A query in the entity query language.
   * @param {string} scope The `QueryScope` the query ranges over.
   * @returns {Promise<Object>} The answer, about the world as it is now.
   */
  query(scene, code, scope) {
    return this.#publisher.send(LiveRoute.QUERY, { [QueryRequestKey.SCENE]: scene, [QueryRequestKey.CODE]: code, [QueryRequestKey.SCOPE]: scope });
  }

  /**
   * @param {string} scene A bundle name, unused.
   * @param {string} scope A `QueryScope` value.
   * @returns {Promise<Array<Object>>} The names a query of that scope may use.
   */
  async vocabulary(scene, scope) {
    const answer = await this.#publisher.read(`${LiveRoute.VOCABULARY}?${new URLSearchParams({ [QuestionsParameter.SCOPE]: scope })}`);
    return answer.entries ?? [];
  }

  /**
   * @param {string} scene A bundle name, unused.
   * @param {string} scope A `QueryScope` value.
   * @param {string} name A variable's or class's name.
   * @returns {Promise<Array<Object>>} The members that may follow the name's dot.
   */
  async members(scene, scope, name) {
    const parameters = new URLSearchParams({ [QuestionsParameter.SCOPE]: scope, [QuestionsParameter.NAME]: name });
    const answer = await this.#publisher.read(`${LiveRoute.MEMBERS}?${parameters}`);
    return answer.members ?? answer.entries ?? [];
  }

  /**
   * @param {string} scene The bundle the publisher's world is shown as.
   * @param {string} text A question in plain language.
   * @returns {Promise<Object>} The matched preset, or why none matched.
   */
  question(scene, text) {
    return this.#publisher.send(LiveRoute.QUESTION, { [QuestionRequestKey.SCENE]: scene, [QuestionRequestKey.TEXT]: text });
  }
}
