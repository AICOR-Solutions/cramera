/**
 * The plans of a replayed recording as the builder's step cards: each step with the
 * fields its action was given, the others folded under "More options", and the
 * constraints attached to it; the step at the playhead is marked running and kept in
 * sight, and a click on a step jumps to its first frame.
 */

import { BooleanText, ConstraintObservationKey, FieldValueKind, PlanNodeKey } from '../../../protocol.js';
import { DomEvent, Elements } from './elements.js';
import { RecordedPlans, StepPhase } from './recorded-plan.js';
import { STEP_PALETTE_SIZE, StepCard, StepCardClass } from './step-card.js';

/**
 * The classes the view's elements carry.
 */
const ViewClass = Object.freeze({
  VIEW: 'recorded-plan',
  LIST: 'steps',
  TITLE: 'plan-title',
  EMPTY: 'empty',
  DEFAULT: 'default',
});

/**
 * The text that unfolds the fields an action may be left without, as in the builder.
 */
const MORE_OPTIONS = 'More options';

/**
 * The kinds of value shown in a select, as the builder asks for a member or an object.
 */
const CHOSEN_KINDS = Object.freeze([FieldValueKind.ENUMERATION, FieldValueKind.ENTITY, FieldValueKind.CLASS]);

/**
 * The input types the replay shows a field's value in.
 */
const InputType = Object.freeze({ NUMBER: 'number', CHECKBOX: 'checkbox', TEXT: 'text' });

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
    const fields = step.fields();
    view.card.append(...(fields.length > 0 ? this.#fieldParts(fields) : this.#parameterParts(step)));
    const constraints = step.constraints();
    if (constraints.length > 0) view.card.append(this.#chips(constraints));
    if (step.hasFrames()) {
      view.card.title = 'Jump to this step';
      elements.listen(view.card, DomEvent.CLICK, () => this.#onSeek(step.start));
    }
    this.#cards.set(step, view);
    return view.card;
  }

  /**
   * @param {Array<import('./recorded-plan.js').RecordedField>} fields Every field of a
   *   step's action.
   * @returns {Array<HTMLElement>} The required fields, and the others folded under
   *   "More options"; a part without fields is left out.
   */
  #fieldParts(fields) {
    const elements = this.#shown;
    const required = fields.filter((field) => field.required);
    const optional = fields.filter((field) => !field.required);
    const parts = [];
    if (required.length > 0) parts.push(this.#fieldBox(required));
    if (optional.length === 0) return parts;
    const more = elements.create('details', StepCardClass.MORE);
    more.open = false;
    more.append(elements.create('summary', '', MORE_OPTIONS), this.#fieldBox(optional));
    elements.listen(more, DomEvent.CLICK, (event) => event.stopPropagation());
    parts.push(more);
    return parts;
  }

  /**
   * @param {Array<import('./recorded-plan.js').RecordedField>} fields Fields of a step's
   *   action.
   * @returns {HTMLElement} Each field labelled with its value, or with its default when
   *   the action kept it.
   */
  #fieldBox(fields) {
    const box = this.#shown.create('div', StepCardClass.PARAMETERS);
    box.append(...fields.map((field) => this.#field(field)));
    return box;
  }

  /**
   * @param {import('./recorded-plan.js').RecordedField} field A field of a step's action.
   * @returns {HTMLElement} The field as the builder's form shows it, but not editable:
   *   a member, an object or a class in a select, a number in a number input with its
   *   default as placeholder, a switch as a checkbox, a grasp or another structured
   *   value as a note, and anything else in a text input.
   */
  #field(field) {
    const elements = this.#shown;
    if (field.kind === FieldValueKind.STRUCTURE) {
      const note = elements.create('p', StepCardClass.DERIVED, `${field.label}: ${field.text()}`);
      note.dataset.field = field.name;
      return note;
    }
    const control = this.#control(field);
    control.disabled = true;
    control.dataset.field = field.name;
    if (field.isDefault()) control.classList.add(ViewClass.DEFAULT);
    return elements.label(field.label, control);
  }

  /**
   * @param {import('./recorded-plan.js').RecordedField} field A field that is not a
   *   structured value.
   * @returns {HTMLElement} The control showing the field's value or default.
   */
  #control(field) {
    const elements = this.#shown;
    if (CHOSEN_KINDS.includes(field.kind)) {
      const select = elements.create('select');
      select.append(elements.create('option', '', field.text()));
      return select;
    }
    const input = elements.create('input');
    if (field.kind === FieldValueKind.BOOLEAN) {
      input.type = InputType.CHECKBOX;
      input.checked = (field.value ?? field.default) === BooleanText.YES;
      return input;
    }
    input.type = field.kind === FieldValueKind.NUMBER ? InputType.NUMBER : InputType.TEXT;
    input.value = field.value ?? '';
    input.placeholder = field.default ?? field.text();
    return input;
  }

  /**
   * @param {import('./recorded-plan.js').RecordedStep} step A step recorded before
   *   actions declared their fields.
   * @returns {Array<HTMLElement>} The fields it was given, or its arm and target; none
   *   when it was recorded with neither.
   */
  #parameterParts(step) {
    const elements = this.#shown;
    const parameters = step.parameters();
    if (parameters.length === 0) return [];
    const box = elements.create('div', StepCardClass.PARAMETERS);
    box.append(...parameters.map((parameter) => elements.label(parameter.name, elements.create('output', '', parameter.value))));
    return [box];
  }

  /**
   * @param {Array<Object>} constraints The constraint monitors attached to a step.
   * @returns {HTMLElement} Each constraint as the builder shows it: its text, its
   *   monitor and what it observed last.
   */
  #chips(constraints) {
    const elements = this.#shown;
    const chips = elements.create('div', StepCardClass.CHIPS);
    chips.append(
      ...constraints.map((constraint) => {
        const chip = elements.create('span', StepCardClass.CHIP);
        chip.append(elements.create('span', '', constraint[ConstraintObservationKey.TEXT]));
        const monitor = constraint[ConstraintObservationKey.MONITOR];
        if (monitor) chip.append(elements.create('span', StepCardClass.BADGE, monitor));
        const observed = constraint[ConstraintObservationKey.OBSERVATION];
        if (observed) {
          const observation = elements.create('span', StepCardClass.OBSERVATION, observed);
          observation.dataset.observation = observed;
          chip.append(observation);
        }
        return chip;
      }),
    );
    return chips;
  }

  /**
   * Remove every listener.
   */
  dispose() {
    this.#shown.dispose();
    this.#frame.dispose();
  }
}
