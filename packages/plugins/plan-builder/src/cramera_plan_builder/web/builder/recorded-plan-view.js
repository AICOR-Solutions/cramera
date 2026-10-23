/**
 * The plans of a replayed recording as the builder's step cards: the step at the
 * playhead is marked running and kept in sight, and a click on a step jumps to its first
 * frame.
 */

import { PlanNodeKey } from '../../../protocol.js';
import { DomEvent, Elements } from './elements.js';
import { RecordedPlans, StepPhase } from './recorded-plan.js';
import { STEP_PALETTE_SIZE, StepCard } from './step-card.js';

/**
 * The classes the view's elements carry.
 */
const ViewClass = Object.freeze({
  VIEW: 'recorded-plan',
  LIST: 'steps',
  TITLE: 'plan-title',
  PARAMETERS: 'step-parameters',
  EMPTY: 'empty',
});

/**
 * How a running step is scrolled into sight: only as far as needed.
 */
const SCROLL_INTO_SIGHT = Object.freeze({ block: 'nearest' });

// %% view

export class RecordedPlanView {
  /**
   * The view's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * Called with the frame a person jumps to.
   * @type {function(number): void}
   */
  #onSeek;

  /**
   * Builds the view's own element.
   * @type {Elements}
   */
  #frame;

  /**
   * Owns the listeners of the shown cards, replaced with every plan shown.
   * @type {Elements}
   */
  #shown;

  /**
   * The shown steps.
   * @type {RecordedPlans}
   */
  #plans = RecordedPlans.of([]);

  /**
   * The card of every shown step.
   * @type {Map<import('./recorded-plan.js').RecordedStep, StepCard>}
   */
  #cards = new Map();

  /**
   * @param {Document} document The page's document.
   * @param {function(number): void} onSeek Called with the frame a person jumps to.
   */
  constructor(document, onSeek) {
    this.#onSeek = onSeek;
    this.#frame = new Elements(document);
    this.#shown = new Elements(document);
    this.element = this.#frame.create('section', ViewClass.VIEW);
  }

  /**
   * Show a recording's plans, each titled with the robot that performed it, and each
   * step with the state it ended in.
   * @param {Array<Object>} roots The roots of the recording's plan trees.
   */
  show(roots) {
    this.#shown.dispose();
    this.#shown = new Elements(this.#frame.document);
    this.#plans = RecordedPlans.of(roots);
    this.#cards = new Map();
    if (!this.hasPlan()) {
      this.element.replaceChildren();
      return;
    }
    const elements = this.#shown;
    const parts = [elements.create('h3', '', 'Recorded plan')];
    if (!this.#plans.hasFrames()) parts.push(elements.create('p', ViewClass.EMPTY, 'This recording does not say when each step ran, so the steps do not follow the playhead.'));
    const palette = new Map();
    const several = this.#plans.plans.length > 1;
    for (const plan of this.#plans.plans) {
      if (several || plan.robot !== null) parts.push(elements.create('h4', ViewClass.TITLE, plan.title()));
      const list = elements.create('ol', ViewClass.LIST);
      list.append(...plan.steps.map((step) => this.#card(step, palette)));
      parts.push(list);
    }
    this.element.replaceChildren(...parts);
  }

  /**
   * @returns {boolean} Whether a shown plan has steps.
   */
  hasPlan() {
    return this.#plans.steps().length > 0;
  }

  /**
   * Mark every step as waiting, running or done at a frame of the replay, and bring a
   * step that starts running into sight.
   * @param {number} frame The frame at the playhead.
   */
  showFrame(frame) {
    for (const [step, view] of this.#cards) {
      const phase = step.phaseAt(frame);
      if (phase === null || view.card.dataset.phase === phase) continue;
      view.card.dataset.phase = phase;
      view.showStatus(phase === StepPhase.DONE ? step.status : phase);
      if (phase === StepPhase.RUNNING) view.card.scrollIntoView(SCROLL_INTO_SIGHT);
    }
  }

  /**
   * @param {import('./recorded-plan.js').RecordedStep} step A recorded step.
   * @param {Map<string, number>} palette The colour of every action shown so far; an
   *   action takes the colour of its first appearance.
   * @returns {HTMLElement} The step's card.
   */
  #card(step, palette) {
    const elements = this.#shown;
    if (!palette.has(step.action)) palette.set(step.action, palette.size % STEP_PALETTE_SIZE);
    const view = new StepCard(elements, step.number, step.label, step.action, palette.get(step.action));
    view.card.dataset.node = step.node[PlanNodeKey.IDENTIFIER];
    view.showStatus(step.status);
    const parameters = step.parameters();
    if (parameters.length > 0) {
      const box = elements.create('div', ViewClass.PARAMETERS);
      box.append(...parameters.map((parameter) => elements.label(parameter.name, elements.create('output', '', parameter.value))));
      view.card.append(box);
    }
    if (step.hasFrames()) {
      view.card.title = 'Jump to this step';
      elements.listen(view.card, DomEvent.CLICK, () => this.#onSeek(step.start));
    }
    this.#cards.set(step, view);
    return view.card;
  }

  /**
   * Remove every listener.
   */
  dispose() {
    this.#shown.dispose();
    this.#frame.dispose();
  }
}
