/**
 * The question panel in the viewer's query slot: a box for queries in the entity query
 * language with its Run button, a box for questions in plain language, the question
 * read back in English, the scene's ready-made questions and the answer. With recorded
 * answers only the ready-made questions can be asked, and the boxes say why.
 */

import {
  PresetCatalogKey,
  QueryScope,
  PresetKey,
  QueryAnswerKey,
  QuestionMatchKey,
  ReplayWindowKey,
  ScopeDescriptionKey,
  VerbalizationKey,
  ViewerEvent,
} from '../../protocol.js';
import { AnswerView } from './answer-view.js';
import { QueryCompletion } from './query-completion.js';

/**
 * What the panel says while nothing was asked yet.
 */
export const Hint = Object.freeze({
  QUESTION: 'The question you ask appears here in English — run a query, or pick one below.',
  ANSWER: 'Choose a question, ask one, or write a query.',
  RECORDED: 'Recorded answers: this page cannot evaluate queries, so the ready-made questions show the answers recorded with cramera-record-answers. Run the viewer in a CRAM workspace to ask your own.',
  QUERY_DISABLED: 'Queries need the viewer running in a CRAM workspace; pick a recorded question below.',
});

/**
 * The scope whose questions are asked of the world at the shown frame.
 */
export const PAUSED_WORLD_SCOPE = QueryScope.PAUSED_WORLD;

/**
 * The scopes a recorded scene answers about its world as it stands at the shown frame:
 * the paused world rebuilt from the bundle, and the recorded world itself.
 */
export const WORLD_AT_FRAME_SCOPES = Object.freeze([PAUSED_WORLD_SCOPE, QueryScope.CURRENT_STATE]);

/**
 * What the panel says of the moment a query about the running process is asked at.
 */
export const RUNNING_MOMENT = 'Asked of the running world itself — the program is held still while the query is answered.';

/**
 * What the status in the card's head says.
 */
export const Status = Object.freeze({
  LIVE: 'EQL ready',
  RUNNING: 'EQL · running world',
  LOADING: 'loading…',
  UNAVAILABLE: 'EQL unavailable',
});

// %% panel

export class QuestionsPanel {
  /**
   * The panel's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * The status shown in the card's head.
   * @type {HTMLElement}
   */
  status;

  /**
   * The application's event bus.
   * @type {import('../../core/event-bus.js').EventBus}
   */
  #bus;

  /**
   * Where the shown scene's questions are answered, or null before one is shown.
   * @type {Object|null}
   */
  #client = null;

  /**
   * The shown bundle, or null before one is shown.
   * @type {string|null}
   */
  #scene = null;

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
   * The typed question and its button.
   * @type {{input: HTMLInputElement, button: HTMLButtonElement}}
   */
  #question;

  /**
   * The typed query and its button.
   * @type {{input: HTMLTextAreaElement, button: HTMLButtonElement}}
   */
  #code;

  /**
   * The question read back in English.
   * @type {HTMLElement}
   */
  #reading;

  /**
   * The note saying the answers are recorded.
   * @type {HTMLElement}
   */
  #note;

  /**
   * The answer.
   * @type {AnswerView}
   */
  #answer;

  /**
   * The hints shown while a query is written.
   * @type {QueryCompletion}
   */
  #completion;

  /**
   * The frame of the recording the viewer shows, which questions about the paused
   * world are asked at.
   * @type {number}
   */
  #frame = 0;

  /**
   * Says which frame a question about the paused world is asked at.
   * @type {HTMLElement}
   */
  #moment;

  /**
   * @param {Document} document The page.
   * @param {import('../../core/event-bus.js').EventBus} bus The application's event bus.
   */
  constructor(document, bus) {
    this.#bus = bus;
    this.element = document.createElement('section');
    this.element.className = 'questions';
    this.status = document.createElement('span');
    this.status.className = 'knowledge-status';
    this.status.textContent = Status.LOADING;
    const box = document.createElement('div');
    box.className = 'query-box';
    const bar = document.createElement('div');
    bar.className = 'query-bar';
    const code = document.createElement('textarea');
    code.rows = 2;
    code.spellcheck = false;
    code.placeholder = 'an(Arm)  ·  hints while you type · Ctrl+Space lists names · Ctrl+Enter runs';
    code.setAttribute('aria-label', 'Query in the entity query language');
    const run = document.createElement('button');
    run.type = 'button';
    run.className = 'run';
    run.textContent = 'Run';
    run.addEventListener('click', () => this.run(code.value, this.#scope.value));
    const field = document.createElement('div');
    field.className = 'query-field';
    this.#completion = new QueryCompletion(code, () => this.run(code.value, this.#scope.value));
    field.append(code, this.#completion.element);
    bar.append(field, run);
    this.#code = { input: code, button: run };
    const ask = document.createElement('form');
    ask.className = 'ask';
    const question = document.createElement('input');
    question.type = 'search';
    question.placeholder = 'Ask in plain English, for example: which robot is this?';
    question.setAttribute('aria-label', 'Question');
    const askButton = document.createElement('button');
    askButton.textContent = 'Ask';
    this.#scope = document.createElement('select');
    this.#scope.setAttribute('aria-label', 'Query scope');
    this.#scope.addEventListener('change', () => this.#useScope());
    ask.append(question, this.#scope, askButton);
    ask.addEventListener('submit', (event) => {
      event.preventDefault();
      this.ask(question.value);
    });
    this.#question = { input: question, button: askButton };
    this.#moment = document.createElement('p');
    this.#moment.className = 'query-moment';
    box.append(bar, this.#moment, ask);
    bus.subscribe(ViewerEvent.FRAME_CHANGED, (frame) => {
      this.#frame = frame;
      this.#showMoment();
    });
    const body = document.createElement('div');
    body.className = 'console-body';
    this.#reading = document.createElement('p');
    this.#reading.className = 'question';
    this.#note = document.createElement('p');
    this.#note.className = 'recorded-note';
    this.#note.hidden = true;
    this.#presets = document.createElement('div');
    this.#presets.className = 'presets';
    this.#answer = new AnswerView(document, (window) => this.#replay(window));
    body.append(this.#reading, this.#note, this.#presets, this.#answer.element);
    this.element.append(box, body);
    this.#showReading(null);
    this.#answer.message(Hint.ANSWER);
  }

  /**
   * Show a scene's ready-made questions, answered by the client the scene's source
   * chose.
   * @param {string} scene The shown bundle.
   * @param {import('./recorded-answers.js').SceneSource} source Where the scene's
   *   questions are answered, with its ready-made questions.
   */
  showScene(scene, source) {
    this.#scene = scene;
    this.#client = source.client;
    this.#bus.publish(ViewerEvent.ENTITY_HIGHLIGHTED, []);
    this.#showReading(null);
    this.#answer.message(Hint.ANSWER);
    const readOnly = source.client.readOnly;
    this.#setReadOnly(readOnly);
    const catalog = source.catalog;
    if (catalog[PresetCatalogKey.OK] === false) {
      this.#presets.replaceChildren();
      this.status.textContent = Status.UNAVAILABLE;
      this.#answer.message(catalog[PresetCatalogKey.ERROR] ?? 'This scene cannot be asked.', true);
      return;
    }
    const running = source.client.live === true;
    this.status.textContent = readOnly ? `recorded answers · ${source.recordedAt ?? ''}`.trim() : running ? Status.RUNNING : Status.LIVE;
    this.#showScopes(catalog[PresetCatalogKey.SCOPES] ?? []);
    this.#showPresets(catalog[PresetCatalogKey.PRESETS] ?? [], readOnly, running);
    this.#useScope();
  }

  /**
   * Offer the names of the chosen scope while a query is written.
   */
  #useScope() {
    const client = this.#client;
    const scene = this.#scene;
    const scope = this.#scope.value;
    const readOnly = !client || client.readOnly || !client.vocabulary;
    this.#completion.useSource(readOnly ? null : {
      vocabulary: () => client.vocabulary(scene, scope),
      members: (name) => client.members(scene, scope, name),
    });
    this.#showMoment();
  }

  /**
   * Say which frame a question is asked at: the paused world stands as it is at it, and
   * the recording's own objects are where they are at it.
   */
  #showMoment() {
    if (this.#client?.live) {
      this.#moment.textContent = RUNNING_MOMENT;
      return;
    }
    const paused = WORLD_AT_FRAME_SCOPES.includes(this.#scope.value);
    this.#moment.textContent = paused
      ? `Asked of the world as it is at frame ${this.#frame} — pause anywhere and ask.`
      : `Objects' positions are read at frame ${this.#frame}; their spawn_position is where they started.`;
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
    await this.run(preset[PresetKey.CODE], preset[PresetKey.SCOPE], preset[PresetKey.VERBALIZATION]);
  }

  /**
   * Run a query and show its answer, lighting up what it names.
   * @param {string} code The query.
   * @param {string} scope The `QueryScope` it ranges over.
   * @param {Object|null} reading The query read back in English, if known beforehand.
   * @returns {Promise<void>} Settles once answered.
   */
  async run(code, scope, reading = null) {
    if (!this.#scene || !code.trim()) return;
    this.#code.input.value = code;
    if (this.#scope.value !== scope) {
      this.#scope.value = scope;
      this.#useScope();
    }
    this.#showReading(reading);
    this.#answer.message('Answering…');
    const frame = this.#frame;
    const answer = await this.#client.query(this.#scene, code, scope, frame).catch((error) => ({ [QueryAnswerKey.OK]: false, [QueryAnswerKey.ERROR]: error.message }));
    this.#showReading(answer[QueryAnswerKey.VERBALIZATION] ?? reading);
    this.#answer.show(answer);
    this.#bus.publish(ViewerEvent.ENTITY_HIGHLIGHTED, answer[QueryAnswerKey.HIGHLIGHT] ?? []);
  }

  /**
   * @param {Object|null} reading A query read back in English, or null for the hint.
   */
  #showReading(reading) {
    const text = reading?.[VerbalizationKey.TEXT];
    this.#reading.textContent = text ?? Hint.QUESTION;
    this.#reading.classList.toggle('hint', !text);
  }

  /**
   * @param {boolean} readOnly Whether only the recorded questions can be asked.
   */
  #setReadOnly(readOnly) {
    for (const control of [this.#code.input, this.#code.button, this.#question.input, this.#question.button, this.#scope]) control.disabled = readOnly;
    this.#code.input.placeholder = readOnly ? Hint.QUERY_DISABLED : 'the(entity(robot))';
    this.#code.input.title = readOnly ? Hint.QUERY_DISABLED : '';
    this.#note.hidden = !readOnly;
    this.#note.textContent = Hint.RECORDED;
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
   * @param {boolean} readOnly Whether the answers are recorded, so questions about a
   *   live run cannot be asked.
   * @param {boolean} running Whether the running process answers, so the questions
   *   that need it can be asked.
   */
  #showPresets(presets, readOnly, running = false) {
    const document = this.element.ownerDocument;
    const buttons = presets
      .filter((preset) => running || !preset[PresetKey.REQUIRES_LIVE])
      .map((preset) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'preset';
        button.textContent = preset[PresetKey.TEXT];
        button.addEventListener('click', () => this.run(preset[PresetKey.CODE], preset[PresetKey.SCOPE], preset[PresetKey.VERBALIZATION] ?? null));
        return button;
      });
    this.#presets.replaceChildren(...buttons);
    this.#presets.dataset.recorded = String(readOnly);
  }

  /**
   * Jump to shortly before a row's moment and play it.
   * @param {Object} window The row's replay window, in frames of the shown recording.
   */
  #replay(window) {
    this.#bus.publish(ViewerEvent.FRAME_REQUESTED, window[ReplayWindowKey.FIRST_FRAME]);
    this.#bus.publish(ViewerEvent.PLAYBACK_REQUESTED, true);
  }
}
