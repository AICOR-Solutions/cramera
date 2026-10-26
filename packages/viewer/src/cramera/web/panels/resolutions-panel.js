/**
 * The Plan resolution panel: how the open parts of a running plan were resolved before
 * the robot carried it out. Each resolution plays one part at a time: the part as the
 * plan states it, the backend answering it, how the backend reasoned and its answers,
 * which fill the resolved plan, while the scene lights up what the answers are about.
 * The latest resolution stays shown, to be played again or carried out.
 */

import {
  BackendDescriptionKey,
  PlanLineKey,
  PlanResolutionKey,
  PlanResolutionsKey,
  PresentationKey,
  ResolvedPartKey,
} from '../protocol.js';
import { showAnswerInScene } from './answer-highlight.js';
import { element } from './elements.js';
import { SidePanel } from './panel-host.js';
import { knowledgeSource, reasoningView } from './reasoning-view.js';

/**
 * What the panel says before a resolution is published.
 */
export const NO_RESOLUTION = 'No plan left parts open yet. When one does, each part is shown here with the backend that answered it.';

/**
 * A resolution answered longer ago than this when the panel first sees it is not
 * played on its own, in seconds; it can still be played again.
 */
export const FRESH_SECONDS = 30;

/**
 * How long the panel waits for the next part of a resolution still being answered, in
 * milliseconds.
 */
export const WAIT_MILLISECONDS = 300;

/**
 * What share of a part's time its reasoning takes to appear.
 */
export const REASONING_SHARE = 0.56;

/**
 * Marks an open part in a plan's line, as ``⟦identifier⟧``.
 */
export const PART_MARK = /⟦([^⟧]+)⟧/g;

/**
 * How a plan's lines are shown.
 */
export const PlanReading = Object.freeze({
  /**
   * As stated: each open part marked as answered or still open.
   */
  STATED: 'stated',
  /**
   * As resolved: each answered part filled with its first answer.
   */
  RESOLVED: 'resolved',
});

// %% plan lines

/**
 * @param {Object} resolution A plan resolution.
 * @param {number} count How many of its parts are answered so far.
 * @returns {Map<string, Object>} Those parts by their identity.
 */
export function answeredParts(resolution, count) {
  return new Map(resolution[PlanResolutionKey.PARTS].slice(0, count).map((part) => [part[ResolvedPartKey.IDENTIFIER], part]));
}

/**
 * @param {Object|undefined} part The answered part a mark stands for, if answered.
 * @param {string} reading A `PlanReading` value.
 * @returns {string} What the mark shows.
 */
export function markText(part, reading) {
  if (reading === PlanReading.STATED) return part ? '✓' : '…';
  if (!part) return '';
  return part[ResolvedPartKey.ANSWERS][0] ?? '∅';
}

/**
 * @param {Document} document The page.
 * @param {Object} line A line of a plan.
 * @param {Map<string, Object>} answered The parts answered so far, by identity.
 * @param {string} reading A `PlanReading` value.
 * @param {string|null} asking The identity of the part being answered, if any.
 * @returns {HTMLElement} The line, its open parts marked.
 */
export function planLineView(document, line, answered, reading, asking = null) {
  const view = element(document, 'div', 'plan-line');
  const text = line[PlanLineKey.TEXT];
  let start = 0;
  for (const mark of text.matchAll(PART_MARK)) {
    if (mark.index > start) view.append(text.slice(start, mark.index));
    const identifier = mark[1];
    const part = answered.get(identifier);
    const states = [part ? 'answered' : '', identifier === asking ? 'asking' : ''].filter(Boolean);
    const shown = element(document, 'span', ['part-mark', ...states].join(' '), markText(part, reading));
    shown.dataset.part = identifier;
    view.append(shown);
    start = mark.index + mark[0].length;
  }
  if (start < text.length) view.append(text.slice(start));
  return view;
}

// %% actions

export class ResolutionActions {
  /**
   * @param {function(string): Promise<Object>} execute Carries out the plan of the
   *   resolution with the given identity.
   */
  constructor(execute) {
    /**
     * Carries out the plan of a resolution.
     * @type {function(string): Promise<Object>}
     */
    this.execute = execute;
  }
}

// %% panel

export class ResolutionsPanel {
  /**
   * The panel.
   * @type {SidePanel}
   */
  panel;

  /**
   * The bus the panel lights the scene up on.
   * @type {import('../core/event-bus.js').EventBus}
   */
  #bus;

  /**
   * What the panel asks of the publisher.
   * @type {ResolutionActions}
   */
  #actions;

  /**
   * Starts and stops timers; `window` in the browser.
   * @type {{setTimeout: Function, clearTimeout: Function}}
   */
  #timers;

  /**
   * The current time in seconds since the Unix epoch.
   * @type {function(): number}
   */
  #now;

  /**
   * The newest resolutions published.
   * @type {Object|null}
   */
  published = null;

  /**
   * Whether the publisher carries out a resolved plan on request.
   * @type {boolean}
   */
  #executionOffered = false;

  /**
   * How many parts of each resolution were played, by its identity.
   * @type {Map<string, number>}
   */
  played = new Map();

  /**
   * The resolutions waiting to be played, oldest first.
   * @type {Array<string>}
   */
  queue = [];

  /**
   * The identity of the resolution being played, or null.
   * @type {string|null}
   */
  playing = null;

  /**
   * The timer of the next step of the playing resolution.
   * @type {number|null}
   */
  #timer = null;

  /**
   * Whether another part shows the scene, so no resolution plays.
   * @type {boolean}
   */
  #sceneHeld = false;

  /**
   * @param {Document} document The page.
   * @param {import('../core/event-bus.js').EventBus} bus The bus the panel lights the
   *   scene up on.
   * @param {ResolutionActions} actions What the panel asks of the publisher.
   * @param {{setTimeout: Function, clearTimeout: Function}} timers Starts and stops timers.
   * @param {function(): number} now The current time in seconds since the Unix epoch.
   */
  constructor(document, bus, actions, timers, now) {
    this.#bus = bus;
    this.#actions = actions;
    this.#timers = timers;
    this.#now = now;
    this.panel = new SidePanel('resolutions', 'Plan resolution', element(document, 'section', 'resolutions'));
    this.panel.element.append(element(document, 'p', 'muted', NO_RESOLUTION));
  }

  /**
   * Take the newest resolutions: each new one plays after those waiting, unless it was
   * answered long ago.
   * @param {Object} resolutions The published resolutions.
   * @param {boolean} executionOffered Whether a resolved plan can be carried out.
   */
  show(resolutions, executionOffered) {
    this.published = resolutions;
    this.#executionOffered = executionOffered;
    for (const resolution of resolutions[PlanResolutionsKey.RESOLUTIONS]) this.#notice(resolution);
    this.#playNext();
    if (this.playing === null) this.#showLatest();
  }

  /**
   * Stop playing while another part shows the scene, and carry on once it is free.
   * @param {boolean} held Whether another part shows the scene.
   */
  holdScene(held) {
    this.#sceneHeld = held;
    if (!held) this.#playNext();
  }

  /**
   * Play a resolution again from its first part.
   * @param {string} identifier The resolution's identity.
   */
  replay(identifier) {
    if (this.playing !== null) return;
    this.#play(identifier);
  }

  /**
   * @param {Object} resolution A published resolution.
   */
  #notice(resolution) {
    const identifier = resolution[PlanResolutionKey.IDENTIFIER];
    const parts = resolution[PlanResolutionKey.PARTS];
    if (this.played.has(identifier) || this.queue.includes(identifier) || this.playing === identifier) return;
    if (!parts.length && !resolution[PlanResolutionKey.DONE]) return;
    const answeredAt = parts.length ? parts.at(-1)[ResolvedPartKey.ANSWERED_AT] : this.#now();
    if (this.#now() - answeredAt > FRESH_SECONDS) {
      this.played.set(identifier, parts.length);
      return;
    }
    this.queue.push(identifier);
  }

  #playNext() {
    if (this.#sceneHeld || this.playing !== null || !this.queue.length) return;
    this.#play(this.queue.shift());
  }

  /**
   * @param {string} identifier The identity of the resolution to play.
   */
  #play(identifier) {
    this.playing = identifier;
    this.played.set(identifier, 0);
    this.#render(this.#resolution(identifier), 0, null);
    this.#later(() => this.#nextPart(), this.#presentation(PresentationKey.BEFORE));
  }

  #nextPart() {
    const resolution = this.#resolution(this.playing);
    if (!resolution) {
      this.#finish();
      return;
    }
    const count = this.played.get(this.playing);
    if (count < resolution[PlanResolutionKey.PARTS].length) {
      const part = resolution[PlanResolutionKey.PARTS][count];
      this.played.set(this.playing, count + 1);
      this.#render(resolution, count, part);
      if (!this.#sceneHeld) showAnswerInScene(this.#bus, part[ResolvedPartKey.HIGHLIGHT]);
      this.#later(() => this.#nextPart(), this.#presentation(PresentationKey.PART));
      return;
    }
    if (!resolution[PlanResolutionKey.DONE]) {
      this.#later(() => this.#nextPart(), WAIT_MILLISECONDS);
      return;
    }
    this.#render(resolution, count, null);
    this.#later(() => this.#finish(), this.#presentation(PresentationKey.AFTER));
  }

  #finish() {
    this.playing = null;
    this.#timer = null;
    if (!this.#sceneHeld) showAnswerInScene(this.#bus, null);
    this.#playNext();
    if (this.playing === null) this.#showLatest();
  }

  /**
   * @param {function(): void} step The next step of the playing resolution.
   * @param {number} milliseconds How long until it is taken.
   */
  #later(step, milliseconds) {
    this.#timer = this.#timers.setTimeout(step, milliseconds);
  }

  /**
   * Stop playing and clear the panel, as when the publisher goes.
   */
  stop() {
    if (this.#timer !== null) this.#timers.clearTimeout(this.#timer);
    this.#timer = null;
    this.playing = null;
    this.queue = [];
  }

  /**
   * @param {string} key A `PresentationKey` value.
   * @returns {number} How many milliseconds that stretch of a resolution takes.
   */
  #presentation(key) {
    return this.published[PlanResolutionsKey.PRESENTATION][key];
  }

  /**
   * @param {string} identifier A resolution's identity.
   * @returns {Object|undefined} The newest published version of the resolution, if it
   *   is still published.
   */
  #resolution(identifier) {
    return this.published[PlanResolutionsKey.RESOLUTIONS].find((resolution) => resolution[PlanResolutionKey.IDENTIFIER] === identifier);
  }

  #showLatest() {
    const resolution = this.published?.[PlanResolutionsKey.RESOLUTIONS].at(-1);
    if (!resolution) return;
    this.#render(resolution, resolution[PlanResolutionKey.PARTS].length, null);
  }

  // %% drawing

  /**
   * @param {Object} resolution The resolution shown.
   * @param {number} count How many of its parts are answered so far.
   * @param {Object|null} asking The part being answered, or null.
   */
  #render(resolution, count, asking) {
    const document = this.panel.element.ownerDocument;
    const answered = answeredParts(resolution, asking ? count + 1 : count);
    const stated = answeredParts(resolution, count);
    const askingIdentifier = asking?.[ResolvedPartKey.IDENTIFIER] ?? null;
    const parts = [
      element(document, 'h3', '', resolution[PlanResolutionKey.TITLE]),
      element(document, 'p', 'resolution-status', this.#statusText(resolution, count, asking)),
      this.#backends(document, resolution, count + (asking ? 1 : 0)),
      element(document, 'h4', '', 'Under-specified plan'),
      element(
        document,
        'div',
        'plan-lines',
        null,
        resolution[PlanResolutionKey.UNDERSPECIFIED].map((line) => planLineView(document, line, stated, PlanReading.STATED, askingIdentifier)),
      ),
    ];
    if (asking) parts.push(this.#partView(document, asking));
    parts.push(
      element(document, 'h4', '', 'Resolved plan'),
      element(
        document,
        'div',
        'plan-lines',
        null,
        resolution[PlanResolutionKey.RESOLVED].map((line) => planLineView(document, line, answered, PlanReading.RESOLVED)),
      ),
      this.#buttons(document, resolution, count),
    );
    this.panel.element.replaceChildren(...parts);
  }

  /**
   * @param {Object} resolution The resolution shown.
   * @param {number} count How many of its parts are answered so far.
   * @param {Object|null} asking The part being answered, or null.
   * @returns {string} How far the resolution has come.
   */
  #statusText(resolution, count, asking) {
    if (asking) return `part ${count + 1} · ${asking[ResolvedPartKey.PART]}`;
    if (count < resolution[PlanResolutionKey.PARTS].length || !resolution[PlanResolutionKey.DONE]) return 'the plan as stated';
    return resolution[PlanResolutionKey.EXECUTABLE] ? '✓ every open part answered' : '✗ a part has no answer';
  }

  /**
   * @param {Document} document The page.
   * @param {Object} resolution The resolution shown.
   * @param {number} count How many of its parts are shown answered.
   * @returns {HTMLElement} The backends, each with how many parts it answered so far.
   */
  #backends(document, resolution, count) {
    const answeredBy = resolution[PlanResolutionKey.PARTS].slice(0, count).map((part) => part[ResolvedPartKey.BACKEND][BackendDescriptionKey.NAME]);
    return element(
      document,
      'ul',
      'backends',
      null,
      this.published[PlanResolutionsKey.BACKENDS].map((backend) => {
        const name = backend[BackendDescriptionKey.NAME];
        const answers = answeredBy.filter((answering) => answering === name).length;
        const chip = element(document, 'li', answers ? 'backend answered' : 'backend', `${knowledgeSource(backend[BackendDescriptionKey.SOURCE]).symbol} ${name} ${answers}`);
        chip.dataset.source = backend[BackendDescriptionKey.SOURCE];
        chip.title = knowledgeSource(backend[BackendDescriptionKey.SOURCE]).note;
        return chip;
      }),
    );
  }

  /**
   * @param {Document} document The page.
   * @param {Object} part The part being answered.
   * @returns {HTMLElement} The statement it was asked as, the backend that answered it,
   *   how it reasoned and its answers.
   */
  #partView(document, part) {
    const backend = part[ResolvedPartKey.BACKEND];
    const source = knowledgeSource(backend[BackendDescriptionKey.SOURCE]);
    const answers = part[ResolvedPartKey.ANSWERS];
    const view = element(document, 'div', 'resolved-part', null, [
      element(document, 'p', 'statement', `${part[ResolvedPartKey.PART]}? ${part[ResolvedPartKey.STATEMENT]}`),
      element(document, 'p', 'answered-by', `${source.symbol} ${backend[BackendDescriptionKey.NAME]} · ${source.note} · ${part[ResolvedPartKey.MILLISECONDS]} ms`),
      reasoningView(document, part[ResolvedPartKey.REASONING] ?? null, answers, part[ResolvedPartKey.EVIDENCE] ?? [], this.#presentation(PresentationKey.PART) * REASONING_SHARE),
      element(document, 'p', 'answers', answers.length ? `answer ${answers[0]}${answers.length > 1 ? `, then ${answers.slice(1).join(', ')}` : ''}` : 'no answer'),
    ]);
    view.dataset.source = backend[BackendDescriptionKey.SOURCE];
    return view;
  }

  /**
   * @param {Document} document The page.
   * @param {Object} resolution The resolution shown.
   * @param {number} count How many of its parts are answered so far.
   * @returns {HTMLElement} The buttons playing it again and carrying it out.
   */
  #buttons(document, resolution, count) {
    const identifier = resolution[PlanResolutionKey.IDENTIFIER];
    const replay = element(document, 'button', '', '▶ Show the resolution');
    replay.type = 'button';
    replay.disabled = this.playing !== null;
    replay.addEventListener('click', () => this.replay(identifier));
    const buttons = element(document, 'div', 'resolution-actions', null, [replay]);
    const complete = resolution[PlanResolutionKey.DONE] && count >= resolution[PlanResolutionKey.PARTS].length;
    if (this.#executionOffered && complete && resolution[PlanResolutionKey.EXECUTABLE]) {
      const run = element(document, 'button', 'primary', 'Carry it out');
      run.type = 'button';
      run.addEventListener('click', () => this.#actions.execute(identifier));
      buttons.append(run);
    }
    return buttons;
  }
}
