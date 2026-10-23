/**
 * Answers read from a bundle's `recorded_answers.json` instead of the plugin's routes,
 * for viewers that cannot answer questions themselves, such as the static demo site:
 * the ready-made questions with the answers they received when they were recorded, and
 * the graph views. Nothing else can be asked.
 */

import {
  BundleFile,
  GraphViewKey,
  PresetCatalogKey,
  QueryAnswerKey,
  QuestionMatchKey,
  RecordedAnswerKey,
  RecordedAnswersKey,
} from '../../protocol.js';

/**
 * What the recorded answers say about questions that were not recorded.
 */
export const NotRecorded = Object.freeze({
  SCENE: 'No answers were recorded for this scene.',
  QUERY: 'Only the recorded questions can be answered here; this query was not recorded.',
  QUESTION: 'Only the recorded questions can be answered here; pick one of them.',
  VIEW: 'This view was not recorded for the scene.',
});

// %% client

export class RecordedAnswersClient {
  /**
   * Whether new queries can be answered: never, for recorded answers.
   * @type {boolean}
   */
  readOnly = true;

  /**
   * The viewer's routes, which serve the bundle files.
   * @type {import('../../core/viewer-api.js').ViewerApi}
   */
  #api;

  /**
   * The recorded answers of each bundle read so far, by bundle name.
   * @type {Map<string, Promise<Object|null>>}
   */
  #documents = new Map();

  /**
   * @param {import('../../core/viewer-api.js').ViewerApi} api The viewer's routes.
   */
  constructor(api) {
    this.#api = api;
  }

  /**
   * @param {string} scene A bundle name.
   * @returns {Promise<Object|null>} The bundle's recorded answers, or null when it has
   *   none.
   */
  recorded(scene) {
    if (!this.#documents.has(scene)) {
      this.#documents.set(scene, this.#api.sceneJson(scene, BundleFile.RECORDED_ANSWERS).catch(() => null));
    }
    return this.#documents.get(scene);
  }

  /**
   * @param {string} scene A bundle name.
   * @returns {Promise<Object>} The bundle's ready-made questions as recorded.
   */
  async presets(scene) {
    const recorded = await this.recorded(scene);
    if (!recorded) return { [PresetCatalogKey.OK]: false, [PresetCatalogKey.ERROR]: NotRecorded.SCENE };
    return recorded[RecordedAnswersKey.PRESETS];
  }

  /**
   * @param {string} scene A bundle name.
   * @param {string} view A `GraphViewName` value.
   * @returns {Promise<Object>} The recorded view.
   */
  async graph(scene, view) {
    const recorded = await this.recorded(scene);
    const graph = (recorded?.[RecordedAnswersKey.GRAPHS] ?? []).find((candidate) => candidate[GraphViewKey.VIEW] === view);
    return graph ?? { [GraphViewKey.OK]: false, [GraphViewKey.ERROR]: recorded ? NotRecorded.VIEW : NotRecorded.SCENE };
  }

  /**
   * @param {string} scene A bundle name.
   * @param {string} code A query in the entity query language.
   * @param {string} scope The `QueryScope` the query ranges over.
   * @returns {Promise<Object>} The answer recorded for the query, or why there is none.
   */
  async query(scene, code, scope) {
    const recorded = await this.recorded(scene);
    const answer = (recorded?.[RecordedAnswersKey.ANSWERS] ?? []).find(
      (candidate) => candidate[RecordedAnswerKey.CODE] === code && candidate[RecordedAnswerKey.SCOPE] === scope,
    );
    return answer?.[RecordedAnswerKey.ANSWER] ?? { [QueryAnswerKey.OK]: false, [QueryAnswerKey.ERROR]: NotRecorded.QUERY };
  }

  /**
   * @returns {Promise<Object>} That plain-language questions cannot be matched here.
   */
  async question() {
    return { [QuestionMatchKey.OK]: true, [QuestionMatchKey.MATCHED]: false, [QuestionMatchKey.REPLY]: NotRecorded.QUESTION };
  }
}

// %% choice

/**
 * The client a scene's questions are answered with, and its ready-made questions.
 */
export class SceneSource {
  /**
   * @param {Object} client The client: the plugin's routes or the recorded answers.
   * @param {Object} catalog The scene's ready-made questions as that client lists them.
   * @param {string|null} recordedAt When the answers were recorded, or null for answers
   *   computed now.
   */
  constructor(client, catalog, recordedAt) {
    /**
     * The client.
     * @type {Object}
     */
    this.client = client;
    /**
     * The scene's ready-made questions.
     * @type {Object}
     */
    this.catalog = catalog;
    /**
     * When the answers were recorded, or null.
     * @type {string|null}
     */
    this.recordedAt = recordedAt;
  }
}

/**
 * Chooses where a scene's questions are answered: by the plugin's routes where they
 * answer, otherwise from the scene's recorded answers.
 */
export class AnswerSources {
  /**
   * The plugin's routes, or null on a static site, which has none.
   * @type {import('./questions-client.js').QuestionsClient|null}
   */
  #server;

  /**
   * The recorded answers.
   * @type {RecordedAnswersClient}
   */
  #recorded;

  /**
   * @param {import('./questions-client.js').QuestionsClient|null} server The plugin's
   *   routes, or null where the viewer is served without them.
   * @param {RecordedAnswersClient} recorded The recorded answers.
   */
  constructor(server, recorded) {
    this.#server = server;
    this.#recorded = recorded;
  }

  /**
   * @param {string} scene A bundle name.
   * @param {AbortSignal=} signal Cancels the request when another scene is shown.
   * @returns {Promise<SceneSource>} The routes when they list the scene's questions,
   *   else the recorded answers when the scene has them, else the routes' failure.
   */
  async forScene(scene, signal) {
    const failure = (error) => ({ [PresetCatalogKey.OK]: false, [PresetCatalogKey.ERROR]: error.message });
    const served = this.#server ? await this.#server.presets(scene, signal).catch(failure) : null;
    if (served && served[PresetCatalogKey.OK] !== false) return new SceneSource(this.#server, served, null);
    const recorded = await this.#recorded.recorded(scene);
    if (recorded) return new SceneSource(this.#recorded, recorded[RecordedAnswersKey.PRESETS], recorded[RecordedAnswersKey.RECORDED_AT]);
    return new SceneSource(this.#server ?? this.#recorded, served ?? (await this.#recorded.presets(scene)), null);
  }
}
