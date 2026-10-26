/**
 * The Queries panel: every query the running process asks while it sets up, resolves
 * and carries out its plans, and, while stepping, the process held at each query until a
 * person moves on. The inspector shows where a query is asked (the plan, actions and
 * queries it is asked inside, down to the query and its variables), the code that asks
 * it, the question in English, the backend answering it, its answers and how the
 * backend reasoned, while the scene lights up what the answers are about.
 */

import {
  BackendDescriptionKey,
  CallSiteKey,
  EnclosingStatementKey,
  HeldStepKey,
  QueryStepKey,
  QueryStepsKey,
  QueryVariableKey,
  SourceExcerptKey,
  StepAdvanceKey,
  StepMoment,
  StepPhase,
  SteppingRequestKey,
  VariableRole,
  VerbalizationKey,
} from '../protocol.js';
import { showAnswerInScene } from './answer-highlight.js';
import { element } from './elements.js';
import { SidePanel } from './panel-host.js';
import { knowledgeSource, reasoningView } from './reasoning-view.js';

/**
 * What the panel says before a query is published.
 */
export const NO_QUERIES = 'The running process has published no queries yet.';

/**
 * How many of the latest queries the list shows.
 */
export const LISTED_STEPS = 7;

/**
 * How many values of a variable are shown.
 */
export const SHOWN_VALUES = 8;

/**
 * Over how many milliseconds a backend's reasoning appears.
 */
export const REASONING_MILLISECONDS = 2600;

/**
 * How long the inspector stays on a query the process carried on from, in
 * milliseconds, so a query asked soon after takes its place without it closing.
 */
export const LINGER_MILLISECONDS = 2500;

/**
 * What the process is said to be doing in each phase.
 */
export const PHASE_TEXTS = Object.freeze({
  [StepPhase.SETUP]: 'setting up',
  [StepPhase.RESOLUTION]: 'resolving the plan',
  [StepPhase.EXPANSION]: 'expanding into motions',
  [StepPhase.EXECUTION]: 'carrying it out',
});

// %% steps

/**
 * @param {Object} steps The published query steps.
 * @param {number|null} picked The number of a step picked to look back at, or null.
 * @returns {Object|null} The step to inspect: the one picked, else the one the process
 *   is held at; null for neither.
 */
export function shownStep(steps, picked) {
  const number = picked ?? steps[QueryStepsKey.HELD]?.[HeldStepKey.NUMBER] ?? null;
  if (number === null) return null;
  return steps[QueryStepsKey.STEPS].find((step) => step[QueryStepKey.NUMBER] === number) ?? null;
}

/**
 * @param {Array<Object>} steps Every query asked.
 * @param {Object} step One of them.
 * @returns {Array<Object>} The queries whose answering asked it, outermost first.
 */
export function askingChain(steps, step) {
  const byNumber = new Map(steps.map((each) => [each[QueryStepKey.NUMBER], each]));
  const chain = [];
  let asker = byNumber.get(step[QueryStepKey.ASKER]);
  while (asker) {
    chain.unshift(asker);
    asker = byNumber.get(asker[QueryStepKey.ASKER]);
  }
  return chain;
}

/**
 * @param {Object} step A query step.
 * @returns {string} The question it asks, in words.
 */
export function questionText(step) {
  return step[QueryStepKey.QUESTION]?.[VerbalizationKey.TEXT] ?? `a query answered by ${step[QueryStepKey.BACKEND][BackendDescriptionKey.NAME]}`;
}

/**
 * @param {Object} variable A variable of a query or a part of a statement.
 * @param {boolean} answered Whether its query was answered.
 * @returns {string} What it holds: its values, else that it is still open, else how
 *   many values the query looked at.
 */
export function heldText(variable, answered) {
  const values = variable[QueryVariableKey.VALUES] ?? [];
  if (values.length) {
    const shown = values.slice(0, SHOWN_VALUES).join(', ');
    return values.length > SHOWN_VALUES ? `${shown} +${values.length - SHOWN_VALUES} more` : shown;
  }
  const role = variable[QueryVariableKey.ROLE];
  if (role === VariableRole.SOUGHT && answered) return 'no answer';
  const lookedAt = variable[QueryVariableKey.LOOKED_AT];
  if (role !== VariableRole.SOUGHT && role !== VariableRole.BEING_ANSWERED && lookedAt !== undefined && lookedAt !== null) return `${lookedAt} looked at`;
  return '?';
}

// %% actions

export class QueryStepActions {
  /**
   * @param {function(Object): Promise<Object>} advance Lets the process carry on, given a
   *   step advance request.
   * @param {function(Object): Promise<Object>} changeStepping Changes how the process is
   *   held, given a stepping request.
   */
  constructor(advance, changeStepping) {
    /**
     * Lets the process carry on.
     * @type {function(Object): Promise<Object>}
     */
    this.advance = advance;
    /**
     * Changes how the process is held.
     * @type {function(Object): Promise<Object>}
     */
    this.changeStepping = changeStepping;
  }
}

// %% panel

export class QueryStepsPanel {
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
   * @type {QueryStepActions}
   */
  #actions;

  /**
   * Starts and stops timers; `window` in the browser.
   * @type {{setTimeout: Function, clearTimeout: Function}}
   */
  #timers;

  /**
   * Called with whether the inspector shows the scene, so other parts leave it alone.
   * @type {function(boolean): void}
   */
  #onInspecting;

  /**
   * The newest published steps.
   * @type {Object|null}
   */
  published = null;

  /**
   * The number of a step picked to look back at, or null to follow the process.
   * @type {number|null}
   */
  picked = null;

  /**
   * Whether the inspector shows a step.
   * @type {boolean}
   */
  inspecting = false;

  /**
   * The timer closing the inspector after the process carried on, or null.
   * @type {number|null}
   */
  #lingering = null;

  /**
   * The switch holding the process at every query.
   * @type {HTMLInputElement}
   */
  stepping;

  /**
   * The switch also holding it at nested queries.
   * @type {HTMLInputElement}
   */
  nested;

  /**
   * The button moving the process on.
   * @type {HTMLButtonElement}
   */
  next;

  /**
   * The list of the latest queries.
   * @type {HTMLElement}
   */
  #list;

  /**
   * The inspector.
   * @type {HTMLElement}
   */
  #inspector;

  /**
   * @param {Document} document The page.
   * @param {import('../core/event-bus.js').EventBus} bus The bus the panel lights the
   *   scene up on.
   * @param {QueryStepActions} actions What the panel asks of the publisher.
   * @param {{setTimeout: Function, clearTimeout: Function}} timers Starts and stops timers.
   * @param {function(boolean): void} onInspecting Called with whether the inspector shows
   *   the scene.
   */
  constructor(document, bus, actions, timers, onInspecting) {
    this.#bus = bus;
    this.#actions = actions;
    this.#timers = timers;
    this.#onInspecting = onInspecting;
    this.stepping = this.#switch(document);
    this.nested = this.#switch(document);
    this.nested.checked = true;
    this.next = element(document, 'button', 'primary', 'Next ▸');
    this.next.type = 'button';
    this.next.disabled = true;
    this.next.addEventListener('click', () => this.advance());
    const runOn = element(document, 'button', '', 'Run to the end');
    runOn.type = 'button';
    runOn.addEventListener('click', () => this.runToTheEnd());
    const controls = element(document, 'div', 'query-step-controls', null, [
      element(document, 'label', 'switch', null, [this.stepping, 'Step through']),
      element(document, 'label', 'switch', null, [this.nested, 'into nested queries']),
      this.next,
      runOn,
    ]);
    this.#list = element(document, 'ol', 'query-steps', null, [element(document, 'li', 'empty', NO_QUERIES)]);
    this.#inspector = element(document, 'div', 'query-inspector');
    this.#inspector.hidden = true;
    this.panel = new SidePanel('queries', 'Queries', element(document, 'section', 'queries', null, [controls, this.#inspector, this.#list]));
  }

  /**
   * @param {Document} document The page.
   * @returns {HTMLInputElement} A switch changing how the process is held.
   */
  #switch(document) {
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.addEventListener('change', () => this.#changeStepping());
    return input;
  }

  /**
   * @returns {number|null} The revision shown, for asking only for a newer one.
   */
  get revision() {
    return this.published?.[QueryStepsKey.REVISION] ?? null;
  }

  /**
   * Take the newest steps; steps the viewer shows already change nothing.
   * @param {Object} steps The published query steps.
   */
  show(steps) {
    if (steps[QueryStepsKey.UNCHANGED] || !steps[QueryStepsKey.STEPS].length) return;
    this.published = steps;
    const held = steps[QueryStepsKey.HELD];
    this.next.disabled = !held;
    this.stepping.checked = steps[QueryStepsKey.STEPPING];
    this.nested.checked = steps[QueryStepsKey.HOLDS_NESTED];
    this.#renderList();
    if (this.picked !== null || held) {
      this.#stopLingering();
      this.#inspect();
      return;
    }
    this.#linger();
  }

  /**
   * Inspect an earlier step.
   * @param {number} number The step's number.
   */
  pick(number) {
    this.picked = number;
    this.#stopLingering();
    this.#inspect();
  }

  /**
   * Let the process carry on from the step the viewer shows it held at.
   * @returns {Promise<Object>|null} The request, or null while the process is not held.
   */
  advance() {
    this.picked = null;
    const held = this.published?.[QueryStepsKey.HELD];
    if (!held) return null;
    return this.#actions.advance({ [StepAdvanceKey.HELD]: held });
  }

  /**
   * Stop holding the process at its queries and close the inspector.
   * @returns {Promise<Object>} The request.
   */
  runToTheEnd() {
    this.stepping.checked = false;
    this.picked = null;
    this.#close();
    return this.#changeStepping();
  }

  /**
   * @returns {Promise<Object>} The request changing how the process is held to what the
   *   switches say.
   */
  #changeStepping() {
    return this.#actions.changeStepping({
      [SteppingRequestKey.STEPPING]: this.stepping.checked,
      [SteppingRequestKey.HOLDS_NESTED]: this.nested.checked,
    });
  }

  /**
   * Close the inspector unless the process is held, as when a person is done looking
   * back.
   */
  closeInspector() {
    this.picked = null;
    if (this.published?.[QueryStepsKey.HELD]) this.#inspect();
    else this.#close();
  }

  #linger() {
    if (!this.inspecting || this.#lingering !== null) return;
    this.#lingering = this.#timers.setTimeout(() => {
      this.#lingering = null;
      if (this.picked === null && !this.published[QueryStepsKey.HELD]) this.#close();
    }, LINGER_MILLISECONDS);
  }

  #stopLingering() {
    if (this.#lingering !== null) this.#timers.clearTimeout(this.#lingering);
    this.#lingering = null;
  }

  #close() {
    if (!this.inspecting) return;
    this.inspecting = false;
    this.#inspector.hidden = true;
    showAnswerInScene(this.#bus, null);
    this.#onInspecting(false);
  }

  /**
   * Stop following the publisher, as when it goes.
   */
  stop() {
    this.#stopLingering();
    this.picked = null;
    this.#close();
  }

  // %% drawing

  #renderList() {
    const document = this.panel.element.ownerDocument;
    const held = this.published[QueryStepsKey.HELD]?.[HeldStepKey.NUMBER];
    const latest = this.published[QueryStepsKey.STEPS].slice(-LISTED_STEPS).reverse();
    this.#list.replaceChildren(
      ...latest.map((step) => {
        const number = step[QueryStepKey.NUMBER];
        const answers = step[QueryStepKey.ANSWERS];
        const answered = step[QueryStepKey.MOMENT] === StepMoment.ANSWERED;
        const button = element(document, 'button', '', null, [
          element(document, 'span', 'muted', `#${number + 1}`),
          element(document, 'span', '', `${knowledgeSource(step[QueryStepKey.BACKEND][BackendDescriptionKey.SOURCE]).symbol} ${questionText(step)}`),
          element(document, 'span', 'muted', answered ? `→ ${answers[0] ?? '∅'}` : '…'),
        ]);
        button.type = 'button';
        button.addEventListener('click', () => this.pick(number));
        const item = element(document, 'li', number === held ? 'query-step held' : 'query-step', null, [button]);
        item.dataset.step = String(number);
        item.style.paddingLeft = `${step[QueryStepKey.DEPTH] * 12}px`;
        return item;
      }),
    );
  }

  #inspect() {
    const step = shownStep(this.published, this.picked);
    if (!step) {
      this.#close();
      return;
    }
    const document = this.panel.element.ownerDocument;
    const steps = this.published[QueryStepsKey.STEPS];
    const answered = step[QueryStepKey.MOMENT] === StepMoment.ANSWERED;
    const backend = step[QueryStepKey.BACKEND];
    const source = knowledgeSource(backend[BackendDescriptionKey.SOURCE]);
    const held = this.published[QueryStepsKey.HELD]?.[HeldStepKey.NUMBER] === step[QueryStepKey.NUMBER];
    const parts = [
      element(document, 'p', 'query-step-heading', `${PHASE_TEXTS[step[QueryStepKey.PHASE]]} · ${step[QueryStepKey.DURING]} · query ${step[QueryStepKey.NUMBER] + 1} of ${steps.length}`),
      element(document, 'h4', '', 'Where the query is asked'),
      this.#stack(document, steps, step),
      element(document, 'h4', '', 'Asked in the code'),
      this.#code(document, step),
      element(document, 'h4', '', 'The question'),
      element(document, 'p', 'question', questionText(step)),
      element(document, 'p', 'answered-by', `${source.symbol} ${backend[BackendDescriptionKey.NAME]} · ${step[QueryStepKey.GENERATES] ? 'generates what the query leaves open · ' : ''}${source.note}${step[QueryStepKey.MILLISECONDS] !== undefined && step[QueryStepKey.MILLISECONDS] !== null ? ` · ${step[QueryStepKey.MILLISECONDS]} ms` : ''}`),
      element(document, 'h4', '', 'The answer'),
      element(document, 'p', 'answers', answered ? step[QueryStepKey.ANSWERS].join(', ') || 'no answer' : 'being answered…'),
    ];
    if (answered && step[QueryStepKey.REASONING]) parts.push(reasoningView(document, step[QueryStepKey.REASONING], step[QueryStepKey.ANSWERS], [], REASONING_MILLISECONDS));
    parts.push(element(document, 'p', 'muted', this.#hint(step, held)));
    if (!held) {
      const back = element(document, 'button', '', 'Back to the robot');
      back.type = 'button';
      back.addEventListener('click', () => this.closeInspector());
      parts.push(back);
    }
    this.#inspector.replaceChildren(...parts);
    this.#inspector.hidden = false;
    if (!this.inspecting) {
      this.inspecting = true;
      this.#onInspecting(true);
    }
    showAnswerInScene(this.#bus, answered ? step[QueryStepKey.HIGHLIGHT] : null);
  }

  /**
   * @param {Object} step The step shown.
   * @param {boolean} held Whether the process is held at it.
   * @returns {string} What moving on does.
   */
  #hint(step, held) {
    if (!held) return 'Looking back at an earlier query.';
    return step[QueryStepKey.MOMENT] === StepMoment.ASKED ? 'The robot waits before answering · Next answers it.' : 'The robot waits with the answer · Next lets it go on.';
  }

  /**
   * @param {Document} document The page.
   * @param {Array<Object>} steps Every query asked.
   * @param {Object} step The step shown.
   * @returns {HTMLElement} The statements and queries the step is asked inside,
   *   outermost first, ending in the step with its variables.
   */
  #stack(document, steps, step) {
    const answered = step[QueryStepKey.MOMENT] === StepMoment.ANSWERED;
    const frames = (step[QueryStepKey.ENCLOSING] ?? []).map((statement) => {
      const frame = element(document, 'li', 'stack-frame', null, [
        element(document, 'span', 'muted', statement[EnclosingStatementKey.KIND]),
        element(document, 'strong', '', statement[EnclosingStatementKey.TITLE]),
      ]);
      if (statement[EnclosingStatementKey.STATEMENT]) frame.append(element(document, 'p', 'statement', statement[EnclosingStatementKey.STATEMENT]));
      frame.append(this.#variables(document, statement[EnclosingStatementKey.PARTS] ?? [], true));
      return frame;
    });
    for (const asker of askingChain(steps, step)) {
      const frame = element(document, 'li', 'stack-frame asking', null, [
        element(document, 'span', 'muted', `query #${asker[QueryStepKey.NUMBER] + 1}`),
        element(document, 'strong', '', questionText(asker)),
      ]);
      frame.addEventListener('click', () => this.pick(asker[QueryStepKey.NUMBER]));
      frames.push(frame);
    }
    frames.push(
      element(document, 'li', 'stack-frame current', null, [
        element(document, 'span', 'muted', `this query #${step[QueryStepKey.NUMBER] + 1}`),
        element(document, 'strong', '', questionText(step)),
        this.#variables(document, step[QueryStepKey.VARIABLES] ?? [], answered),
      ]),
    );
    return element(document, 'ol', 'query-stack', null, frames);
  }

  /**
   * @param {Document} document The page.
   * @param {Array<Object>} variables Variables of a query or parts of a statement.
   * @param {boolean} answered Whether the query was answered.
   * @returns {HTMLElement} Each with what it is to its query and what it holds.
   */
  #variables(document, variables, answered) {
    return element(
      document,
      'dl',
      'query-variables',
      null,
      variables.flatMap((variable) => {
        const type = variable[QueryVariableKey.TYPE];
        const name = element(document, 'dt', '', `${variable[QueryVariableKey.NAME]}${type ? `: ${type}` : ''} · ${variable[QueryVariableKey.ROLE]}`);
        name.dataset.role = variable[QueryVariableKey.ROLE];
        return [name, element(document, 'dd', '', heldText(variable, answered))];
      }),
    );
  }

  /**
   * @param {Document} document The page.
   * @param {Object} step The step shown.
   * @returns {HTMLElement} The lines writing the query, the statement in focus, and the
   *   call that asked it.
   */
  #code(document, step) {
    const code = step[QueryStepKey.CODE];
    if (!code) return element(document, 'p', 'muted', 'The code that asked this query cannot be read.');
    const first = code[SourceExcerptKey.FIRST_LINE];
    const lines = code[SourceExcerptKey.LINES].map((text, index) => {
      const number = first + index;
      const focused = number >= code[SourceExcerptKey.FOCUS_FIRST_LINE] && number <= code[SourceExcerptKey.FOCUS_LAST_LINE];
      const line = element(document, 'code', focused ? 'focus' : '', text || ' ');
      line.dataset.line = String(number);
      return line;
    });
    const parts = [element(document, 'p', 'muted', `${code[SourceExcerptKey.FILE]} · ${code[SourceExcerptKey.FUNCTION]}()`), element(document, 'pre', 'query-code', null, lines)];
    const caller = step[QueryStepKey.CALLER];
    if (caller) parts.push(element(document, 'p', 'muted', `asked by ${caller[CallSiteKey.FUNCTION]}() in ${caller[CallSiteKey.MODULE]}, line ${caller[CallSiteKey.LINE]}`));
    return element(document, 'div', 'query-source', null, parts);
  }
}
