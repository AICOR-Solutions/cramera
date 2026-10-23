/**
 * A divider between two panes: dragging it gives one pane more of the room, a double
 * click returns to the default share, and the share is remembered. The scene page has
 * one between the scene and the side column and one between the query slot and the
 * side panels.
 */

import { PageStorageKey } from '../protocol.js';

// %% splits

/**
 * How a divider is laid out: what it measures, where it keeps the share and in which
 * bounds.
 */
export class SplitLayout {
  /**
   * @param {Object} layout
   * @param {string} layout.key The `PageStorageKey` remembering the share.
   * @param {string} layout.property The CSS custom property carrying the share.
   * @param {number} layout.least The least share, in percent.
   * @param {number} layout.most The most share, in percent.
   * @param {number} layout.initial The share before any drag, in percent.
   * @param {function(DOMRect, {clientX: number, clientY: number}): number} layout.measure
   *   The share a pointer at that position asks for, in percent.
   */
  constructor({ key, property, least, most, initial, measure }) {
    this.key = key;
    this.property = property;
    this.least = least;
    this.most = most;
    this.initial = initial;
    this.measure = measure;
  }
}

/**
 * The side column's share of the scene page's width.
 */
export const COLUMNS = new SplitLayout({
  key: PageStorageKey.SPLIT,
  property: '--side-share',
  least: 25,
  most: 75,
  initial: 50,
  measure: (bounds, { clientX }) => ((bounds.right - clientX) / bounds.width) * 100,
});

/**
 * The query slot's share of the side column's height.
 */
export const ROWS = new SplitLayout({
  key: PageStorageKey.QUERY_SPLIT,
  property: '--query-share',
  least: 15,
  most: 85,
  initial: 45,
  measure: (bounds, { clientY }) => ((clientY - bounds.top) / bounds.height) * 100,
});

export class PaneSplit {
  /**
   * The element holding both panes and the divider.
   * @type {HTMLElement}
   */
  #split;

  /**
   * The divider.
   * @type {HTMLElement}
   */
  #divider;

  /**
   * How the divider is laid out.
   * @type {SplitLayout}
   */
  #layout;

  /**
   * The browser's local storage, or null where the page has none.
   * @type {Storage|null}
   */
  #storage;

  /**
   * The share, in percent.
   * @type {number}
   */
  #share;

  /**
   * @param {HTMLElement} split The element holding both panes and the divider.
   * @param {HTMLElement} divider The divider, between the panes.
   * @param {SplitLayout} layout How the divider is laid out.
   * @param {Storage|null} storage The browser's local storage, or null.
   */
  constructor(split, divider, layout, storage) {
    this.#split = split;
    this.#divider = divider;
    this.#layout = layout;
    this.#storage = storage;
    divider.addEventListener('pointerdown', (event) => this.#startDragging(event));
    divider.addEventListener('dblclick', () => this.choose(layout.initial));
    this.#apply(this.#stored() ?? layout.initial);
  }

  /**
   * @returns {number} The share, in percent.
   */
  get share() {
    return this.#share;
  }

  /**
   * Choose a share, show it and remember it.
   * @param {number} share The share in percent; kept within the layout's bounds.
   */
  choose(share) {
    this.#apply(share);
    try {
      this.#storage?.setItem(this.#layout.key, String(this.#share));
    } catch {
      // Storage refused (private window, blocked site data): the share lasts this page.
    }
  }

  /**
   * @param {number} share The share in percent.
   */
  #apply(share) {
    this.#share = Math.min(this.#layout.most, Math.max(this.#layout.least, share));
    this.#split.style.setProperty(this.#layout.property, `${this.#share}%`);
  }

  /**
   * @param {PointerEvent} event The pointer going down on the divider.
   */
  #startDragging(event) {
    event.preventDefault();
    this.#divider.setPointerCapture?.(event.pointerId);
    this.#divider.classList.add('dragging');
    const bounds = this.#split.getBoundingClientRect();
    const move = (moving) => this.#apply(this.#layout.measure(bounds, moving));
    const stop = () => {
      this.#divider.classList.remove('dragging');
      this.#divider.removeEventListener('pointermove', move);
      this.#divider.removeEventListener('pointerup', stop);
      this.#divider.removeEventListener('pointercancel', stop);
      this.choose(this.#share);
    };
    this.#divider.addEventListener('pointermove', move);
    this.#divider.addEventListener('pointerup', stop);
    this.#divider.addEventListener('pointercancel', stop);
  }

  /**
   * @returns {number|null} The remembered share, or null.
   */
  #stored() {
    try {
      const stored = Number.parseFloat(this.#storage?.getItem(this.#layout.key) ?? '');
      return Number.isFinite(stored) ? stored : null;
    } catch {
      return null;
    }
  }
}
