/**
 * The constraints to attach: sentences written in plain language, starting from the
 * rule book's own, each dragged onto a plan step; and how the rule book reads them.
 */

import { ConstraintRuleKey, PlanBuilderCatalogKey, StepConstraintKey } from '../../../protocol.js';
import { DragKind, DragText, DomEvent, Elements, PlanAction } from './elements.js';

/**
 * The storage key of the sentences a person wrote.
 */
export const SENTENCES_KEY = 'cramera.plan-builder.constraints';

/**
 * The key a pressed Enter has.
 */
const ENTER = 'Enter';

/**
 * The badge of a sentence no rule reads.
 */
const NO_RULE = 'no rule';

// %% sentences

export class ConstraintSentences {
  /**
   * The browser's storage.
   * @type {Storage}
   */
  #storage;

  /**
   * The rule book's sentences, each with the monitor it means.
   * @type {Array<Object>}
   */
  #offered;

  /**
   * The sentences the person wrote, each with the monitor it means.
   * @type {Array<Object>}
   */
  #own;

  /**
   * @param {Array<Object>} rules The catalog's constraint rules.
   * @param {Storage} storage The browser's storage.
   */
  constructor(rules, storage) {
    this.#storage = storage;
    this.#offered = rules.map((rule) => ({ [StepConstraintKey.TEXT]: rule[ConstraintRuleKey.SENTENCE], [StepConstraintKey.MONITOR_TYPE]: rule[ConstraintRuleKey.MONITOR_TYPE] }));
    this.#own = JSON.parse(storage.getItem(SENTENCES_KEY) ?? '[]');
  }

  /**
   * @returns {Array<Object>} The rule book's sentences, then the person's.
   */
  all() {
    return [...this.#offered, ...this.#own];
  }

  /**
   * @param {string} text A sentence.
   * @returns {boolean} Whether the person wrote it, so it can be removed.
   */
  isOwn(text) {
    return this.#own.some((sentence) => sentence[StepConstraintKey.TEXT] === text);
  }

  /**
   * Keep a sentence the person wrote, once.
   * @param {Object} compiled The sentence compiled without a step.
   */
  add(compiled) {
    if (this.all().some((sentence) => sentence[StepConstraintKey.TEXT] === compiled[StepConstraintKey.TEXT])) return;
    this.#own.push({ [StepConstraintKey.TEXT]: compiled[StepConstraintKey.TEXT], [StepConstraintKey.MONITOR_TYPE]: compiled[StepConstraintKey.MONITOR_TYPE] });
    this.#store();
  }

  /**
   * @param {string} text A sentence the person wrote, to forget.
   */
  remove(text) {
    this.#own = this.#own.filter((sentence) => sentence[StepConstraintKey.TEXT] !== text);
    this.#store();
  }

  /**
   * Keep the person's sentences in the browser's storage.
   */
  #store() {
    this.#storage.setItem(SENTENCES_KEY, JSON.stringify(this.#own));
  }
}

// %% view

export class ConstraintsView {
  /**
   * The view's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * The page that compiles sentences.
   * @type {Object}
   */
  #editor;

  /**
   * The sentences offered.
   * @type {ConstraintSentences}
   */
  #sentences;

  /**
   * Owns the listeners of the shown cards, replaced on every render.
   * @type {Elements}
   */
  #shown;

  /**
   * Owns the listeners of the input and the explanation.
   * @type {Elements}
   */
  #frame;

  /**
   * The cards of the sentences.
   * @type {HTMLElement}
   */
  #cards;

  /**
   * @param {Document} document The page's document.
   * @param {Object} editor The page: `state` (the `PlanState`) and
   *   `compileSentence(text)`, which answers the sentence compiled without a step.
   * @param {ConstraintSentences} sentences The sentences offered.
   */
  constructor(document, editor, sentences) {
    this.#editor = editor;
    this.#sentences = sentences;
    this.#frame = new Elements(document);
    this.#shown = new Elements(document);
    const elements = this.#frame;
    this.element = elements.create('div', 'constraints');
    this.#cards = elements.create('ul', 'sentences');
    const input = elements.input('text', PlanAction.CONSTRAINT_TEXT, () => {});
    input.placeholder = 'Keep the milk upright';
    const add = () => this.#add(input);
    elements.listen(input, DomEvent.KEY_DOWN, (event) => {
      if (event.key === ENTER) add();
    });
    const row = elements.create('div', 'button-row');
    row.append(input, elements.button('Add', PlanAction.ADD_CONSTRAINT, add));
    this.element.append(this.#cards, row, this.#explanation());
  }

  /**
   * Show the sentences, each draggable onto a step.
   */
  render() {
    this.#shown.dispose();
    this.#shown = new Elements(this.#frame.document);
    const elements = this.#shown;
    this.#cards.replaceChildren(
      ...this.#sentences.all().map((sentence) => {
        const text = sentence[StepConstraintKey.TEXT];
        const card = elements.create('li', 'sentence');
        elements.draggable(card, DragText.of(DragKind.CONSTRAINT, text));
        const badge = elements.create('span', sentence[StepConstraintKey.MONITOR_TYPE] ? 'badge' : 'badge unmatched', sentence[StepConstraintKey.MONITOR_TYPE] ?? NO_RULE);
        card.append(elements.create('span', 'sentence-text', text), badge);
        if (this.#sentences.isOwn(text)) {
          card.append(
            elements.button('×', PlanAction.REMOVE_CONSTRAINT, () => {
              this.#sentences.remove(text);
              this.render();
            }),
          );
        }
        return card;
      }),
    );
  }

  /**
   * @param {HTMLInputElement} input The input holding a new sentence.
   */
  async #add(input) {
    const text = input.value.trim();
    if (!text) return;
    const compiled = await this.#editor.compileSentence(text);
    if (!compiled) return;
    this.#sentences.add(compiled);
    input.value = '';
    this.render();
  }

  /**
   * @returns {HTMLElement} How the rule book reads sentences, folded away.
   */
  #explanation() {
    const elements = this.#frame;
    const details = elements.create('details', 'rule-book');
    details.append(elements.create('summary', '', 'How sentences become constraints'));
    const table = elements.create('table');
    const head = elements.create('tr');
    head.append(elements.create('th', '', 'Wording'), elements.create('th', '', 'Monitor'), elements.create('th', '', 'Effect'));
    table.append(head);
    for (const rule of this.#editor.state.catalog[PlanBuilderCatalogKey.CONSTRAINT_RULES]) {
      const row = elements.create('tr');
      row.append(
        elements.create('td', '', rule[ConstraintRuleKey.EXAMPLES]),
        elements.create('td', 'monitor', rule[ConstraintRuleKey.MONITOR_TYPE]),
        elements.create('td', '', rule[ConstraintRuleKey.EFFECT]),
      );
      table.append(row);
    }
    details.append(table, elements.create('p', 'muted', 'A length in the sentence, such as 10 cm, sets the limit. The object is the one the sentence names, else the one its step acts on. Monitors are observed by the live publisher while the plan runs.'));
    return details;
  }

  /**
   * Remove every listener.
   */
  dispose() {
    this.#shown.dispose();
    this.#frame.dispose();
  }
}
