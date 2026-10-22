/**
 * The resource library: every resource a draft can place, searched by name and
 * filtered by category.
 */

import { ResourceCategory, ResourceKey } from '../../../protocol.js';
import { BuilderAction, DomEvent, Elements } from './elements.js';

/**
 * How many resources the library lists at once; a search narrows the rest.
 */
export const LIBRARY_PAGE_SIZE = 120;

/**
 * The filter's choice of every category.
 */
const EVERY_CATEGORY = '';

/**
 * The filter's text of each category.
 */
export const CATEGORY_LABELS = Object.freeze({
  [EVERY_CATEGORY]: 'All resources',
  [ResourceCategory.ENVIRONMENT]: 'Environments',
  [ResourceCategory.ROBOT]: 'Robots',
  [ResourceCategory.OBJECT]: 'Objects',
  [ResourceCategory.POINT_CLOUD]: 'Point clouds',
});

// %% library

export class LibraryView {
  /**
   * Builds the elements and owns their listeners.
   * @type {import('./elements.js').Elements}
   */
  #elements;

  /**
   * Builds the listed cards and owns their listeners, replaced on every listing.
   * @type {Elements}
   */
  #cards;

  /**
   * Called with the identifier of a resource to place.
   * @type {function(string): void}
   */
  #onAdd;

  /**
   * The resources offered.
   * @type {Array<Object>}
   */
  #resources = [];

  /**
   * The search field.
   * @type {HTMLInputElement}
   */
  #search;

  /**
   * The category filter.
   * @type {HTMLSelectElement}
   */
  #category;

  /**
   * How many resources match.
   * @type {HTMLElement}
   */
  #count;

  /**
   * The listed resources.
   * @type {HTMLElement}
   */
  #list;

  /**
   * The library's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * @param {import('./elements.js').Elements} elements Builds the elements.
   * @param {function(string): void} onAdd Called with the identifier of a resource to place.
   */
  constructor(elements, onAdd) {
    this.#elements = elements;
    this.#cards = new Elements(elements.document);
    this.#onAdd = onAdd;
    this.element = elements.create('section', 'builder-section library');
    const heading = elements.create('div', 'section-heading');
    this.#count = elements.create('span', 'muted');
    heading.append(elements.create('h2', '', 'Resource library'), this.#count);
    this.#search = elements.create('input');
    this.#search.type = 'search';
    this.#search.dataset.action = BuilderAction.SEARCH;
    this.#search.placeholder = 'Robot, table, cabinet…';
    elements.listen(this.#search, DomEvent.INPUT, () => this.#render());
    this.#category = elements.select(BuilderAction.FILTER, () => this.#render());
    elements.options(
      this.#category,
      Object.entries(CATEGORY_LABELS).map(([value, label]) => ({ value, label })),
      EVERY_CATEGORY,
    );
    this.#list = elements.create('div', 'resource-list');
    this.element.append(heading, elements.label('Search', this.#search), elements.label('Category', this.#category), this.#list);
  }

  /**
   * Remove the listeners of the listed cards; the search and filter listeners belong to
   * the elements given to the constructor.
   */
  dispose() {
    this.#cards.dispose();
  }

  /**
   * @param {Array<Object>} resources The catalog's resources.
   */
  show(resources) {
    this.#resources = resources;
    this.#render();
  }

  /**
   * @returns {Array<Object>} The resources the search and filter let through.
   */
  matching() {
    const words = this.#search.value.trim().toLowerCase();
    const category = this.#category.value;
    return this.#resources.filter(
      (resource) =>
        (category === EVERY_CATEGORY || resource[ResourceKey.CATEGORY] === category) &&
        `${resource[ResourceKey.NAME]} ${resource[ResourceKey.IDENTIFIER]}`.toLowerCase().includes(words),
    );
  }

  /**
   * List the first page of matching resources.
   */
  #render() {
    this.#cards.dispose();
    const matching = this.matching();
    this.#count.textContent = `${matching.length} of ${this.#resources.length}`;
    const cards = matching.slice(0, LIBRARY_PAGE_SIZE).map((resource) => this.#card(resource));
    if (matching.length === 0) cards.push(this.#elements.create('p', 'muted', 'No resource matches.'));
    if (matching.length > LIBRARY_PAGE_SIZE) cards.push(this.#elements.create('p', 'muted', `Showing the first ${LIBRARY_PAGE_SIZE}; search to narrow the list.`));
    this.#list.replaceChildren(...cards);
  }

  /**
   * @param {Object} resource A catalog resource.
   * @returns {HTMLButtonElement} The button placing it.
   */
  #card(resource) {
    const button = this.#cards.button('', BuilderAction.ADD, () => this.#onAdd(resource[ResourceKey.IDENTIFIER]));
    button.className = 'resource-card';
    button.title = resource[ResourceKey.IDENTIFIER];
    const name = this.#cards.create('span', 'resource-name', resource[ResourceKey.NAME]);
    const kind = this.#cards.create('span', 'resource-kind', `${resource[ResourceKey.CATEGORY]} · ${resource[ResourceKey.KIND]}`);
    button.append(name, kind);
    return button;
  }
}
