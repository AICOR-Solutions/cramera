/**
 * The Questions panel: ready-made questions of the shown scene, a box for questions in
 * plain language, a box for queries in the entity query language, and the answer.
 */

import {
  PresetCatalogKey,
  PresetKey,
  QueryAnswerKey,
  QuestionMatchKey,
  ReplayWindowKey,
  ScopeDescriptionKey,
  ViewerEvent,
} from '../../protocol.js';
import { AnswerView } from './answer-view.js';

// %% panel

export class QuestionsPanel {
  /**
   * The panel's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * The plugin's routes.
   * @type {import('./questions-client.js').QuestionsClient}
   */
  #client;

  /**
   * The application's event bus.
   * @type {import('../../core/event-bus.js').EventBus}
   */
  #bus;

  /**
   * The shown bundle, or null before one is shown.
   * @type {string|null}
   */
  #scene = null;

  /**
   * Cancels loading the presets of a scene that was replaced.
   * @type {AbortController|null}
   */
  #loading = null;

  /**
   * The ready-made questions.
   * @type {HTMLElement}
   */
  #presets;

  /**
   * The scope choice of typed queries.
   * @type {HTMLSelectElement}
   */
  #scope;

  /**
   * The typed question.
   * @type {HTMLInputElement}
   */
  #question;

  /**
   * The typed query.
   * @type {HTMLTextAreaElement}
   */
  #code;

  /**
   * The answer.
   * @type {AnswerView}
   */
  #answer;

  /**
   * @param {Document} document The page.
   * @param {import('./questions-client.js').QuestionsClient} client The plugin's routes.
   * @param {import('../../core/event-bus.js').EventBus} bus The application's event bus.
   */
  constructor(document, client, bus) {
    this.#client = client;
    this.#bus = bus;
    this.element = document.createElement('section');
    this.element.className = 'questions';
    this.#presets = document.createElement('div');
    this.#presets.className = 'presets';
    this.#question = document.createElement('input');
    this.#question.type = 'search';
    this.#question.placeholder = 'Ask, for example: which robot is this?';
    this.#question.setAttribute('aria-label', 'Question');
    const ask = document.createElement('form');
    ask.className = 'ask';
    const askButton = document.createElement('button');
    askButton.textContent = 'Ask';
    ask.append(this.#question, askButton);
    ask.addEventListener('submit', (event) => {
      event.preventDefault();
      this.ask(this.#question.value);
    });
    this.#scope = document.createElement('select');
    this.#scope.setAttribute('aria-label', 'Query scope');
    this.#code = document.createElement('textarea');
    this.#code.rows = 4;
    this.#code.spellcheck = false;
    this.#code.setAttribute('aria-label', 'Query in the entity query language');
    const run = document.createElement('button');
    run.textContent = 'Run query';
    run.addEventListener('click', () => this.run(this.#code.value, this.#scope.value));
    const editor = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Query';
    editor.append(summary, this.#scope, this.#code, run);
    this.#answer = new AnswerView(document, (window) => this.#replay(window));
    this.element.append(this.#presets, ask, editor, this.#answer.element);
    this.#answer.message('Choose a question, ask one, or write a query.');
  }

  /**
   * Show the ready-made questions of a scene.
   * @param {string} scene The shown bundle.
   * @returns {Promise<void>} Settles once the presets are shown or have failed.
   */
  async showScene(scene) {
    this.#loading?.abort();
    const loading = new AbortController();
    this.#loading = loading;
    this.#scene = scene;
    this.#bus.publish(ViewerEvent.ENTITY_HIGHLIGHTED, []);
    this.#answer.message('Choose a question, ask one, or write a query.');
    const catalog = await this.#client.presets(scene, loading.signal).catch((error) => (loading.signal.aborted ? null : { [PresetCatalogKey.OK]: false, [PresetCatalogKey.ERROR]: error.message }));
    if (!catalog || loading.signal.aborted) return;
    if (catalog[PresetCatalogKey.OK] === false) {
      this.#presets.replaceChildren();
      this.#answer.message(catalog[PresetCatalogKey.ERROR] ?? 'This scene cannot be asked.', true);
      return;
    }
    this.#showScopes(catalog[PresetCatalogKey.SCOPES] ?? []);
    this.#showPresets(catalog[PresetCatalogKey.PRESETS] ?? []);
  }

  /**
   * Answer a plain-language question through the preset it matches.
   * @param {string} text The question.
   * @returns {Promise<void>} Settles once answered.
   */
  async ask(text) {
    if (!this.#scene || !text.trim()) return;
    this.#answer.message('Thinking…');
    const match = await this.#client.question(this.#scene, text).catch((error) => ({ [QuestionMatchKey.OK]: false, [QuestionMatchKey.REPLY]: error.message }));
    const preset = match[QuestionMatchKey.PRESET];
    if (!match[QuestionMatchKey.MATCHED] || !preset) {
      this.#answer.message(match[QuestionMatchKey.REPLY] ?? 'No ready-made question matches.', match[QuestionMatchKey.OK] === false);
      return;
    }
    await this.run(preset[PresetKey.CODE], preset[PresetKey.SCOPE]);
  }

  /**
   * Run a query and show its answer, lighting up what it names.
   * @param {string} code The query.
   * @param {string} scope The `QueryScope` it ranges over.
   * @returns {Promise<void>} Settles once answered.
   */
  async run(code, scope) {
    if (!this.#scene || !code.trim()) return;
    this.#code.value = code;
    this.#scope.value = scope;
    this.#answer.message('Answering…');
    const answer = await this.#client.query(this.#scene, code, scope).catch((error) => ({ [QueryAnswerKey.OK]: false, [QueryAnswerKey.ERROR]: error.message }));
    this.#answer.show(answer);
    this.#bus.publish(ViewerEvent.ENTITY_HIGHLIGHTED, answer[QueryAnswerKey.HIGHLIGHT] ?? []);
  }

  /**
   * @param {Array<Object>} scopes The scopes a query may range over.
   */
  #showScopes(scopes) {
    const document = this.element.ownerDocument;
    this.#scope.replaceChildren(
      ...scopes.map((scope) => {
        const option = document.createElement('option');
        option.value = scope[ScopeDescriptionKey.NAME];
        option.textContent = scope[ScopeDescriptionKey.LABEL];
        return option;
      }),
    );
  }

  /**
   * @param {Array<Object>} presets The ready-made questions.
   */
  #showPresets(presets) {
    const document = this.element.ownerDocument;
    const buttons = presets
      .filter((preset) => !preset[PresetKey.REQUIRES_LIVE])
      .map((preset) => {
        const button = document.createElement('button');
        button.className = 'preset';
        button.textContent = preset[PresetKey.TEXT];
        button.addEventListener('click', () => this.run(preset[PresetKey.CODE], preset[PresetKey.SCOPE]));
        return button;
      });
    this.#presets.replaceChildren(...buttons);
  }

  /**
   * Jump to the start of a row's moment and play it.
   * @param {Object} window The row's replay window.
   */
  #replay(window) {
    this.#bus.publish(ViewerEvent.FRAME_REQUESTED, window[ReplayWindowKey.START]);
    this.#bus.publish(ViewerEvent.PLAYBACK_REQUESTED, true);
  }
}
