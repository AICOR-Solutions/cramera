/**
 * How far the page is: written to the root element's data attributes for tools such
 * as the screenshot command, and shown in the status line for people.
 */

import { PageState, PageStateAttribute } from '../protocol.js';

// %% status

export class PageStatus {
  /**
   * The root element whose data attributes carry the state.
   * @type {HTMLElement}
   */
  #root;

  /**
   * The element showing the status line.
   * @type {HTMLElement}
   */
  #line;

  /**
   * @param {HTMLElement} root The page's root element.
   * @param {HTMLElement} line The element showing the status line.
   */
  constructor(root, line) {
    this.#root = root;
    this.#line = line;
  }

  /**
   * @param {string} text What the page is loading.
   */
  loading(text) {
    this.#show(PageState.LOADING, text);
  }

  /**
   * @param {string} text What the page shows.
   */
  ready(text) {
    this.#show(PageState.READY, text);
  }

  /**
   * @param {string} text Why the page cannot show its scene.
   */
  failed(text) {
    this.#show(PageState.FAILED, text);
  }

  /**
   * @returns {string|undefined} The current `PageState` value.
   */
  get state() {
    return this.#root.dataset[PageStateAttribute.STATE];
  }

  /**
   * @param {string} state A `PageState` value.
   * @param {string} text The status line.
   */
  #show(state, text) {
    this.#root.dataset[PageStateAttribute.STATE] = state;
    this.#root.dataset[PageStateAttribute.STATUS] = text;
    this.#line.textContent = text;
    this.#line.dataset.state = state;
  }
}
