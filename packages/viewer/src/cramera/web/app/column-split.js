/**
 * The divider between the scene and the side column: dragging it gives one side more
 * of the page's width, a double click returns to halves, and the share is remembered.
 */

import { PageStorageKey } from '../protocol.js';

// %% split

/**
 * The least and the most of the page's width the side column may take, in percent.
 */
export const SIDE_SHARE = Object.freeze({ LEAST: 25, MOST: 75, HALF: 50 });

export class ColumnSplit {
  /**
   * The element holding both columns and the divider, a grid.
   * @type {HTMLElement}
   */
  #split;

  /**
   * The divider.
   * @type {HTMLElement}
   */
  #divider;

  /**
   * The browser's local storage, or null where the page has none.
   * @type {Storage|null}
   */
  #storage;

  /**
   * The side column's share of the width, in percent.
   * @type {number}
   */
  #share = SIDE_SHARE.HALF;

  /**
   * @param {HTMLElement} split The element holding both columns and the divider.
   * @param {HTMLElement} divider The divider, between the columns.
   * @param {Storage|null} storage The browser's local storage, or null.
   */
  constructor(split, divider, storage) {
    this.#split = split;
    this.#divider = divider;
    this.#storage = storage;
    divider.addEventListener('pointerdown', (event) => this.#startDragging(event));
    divider.addEventListener('dblclick', () => this.choose(SIDE_SHARE.HALF));
    this.#apply(this.#stored() ?? SIDE_SHARE.HALF);
  }

  /**
   * @returns {number} The side column's share of the width, in percent.
   */
  get share() {
    return this.#share;
  }

  /**
   * Give the side column a share of the width, show it and remember it.
   * @param {number} share The share in percent; kept within `SIDE_SHARE`.
   */
  choose(share) {
    this.#apply(share);
    try {
      this.#storage?.setItem(PageStorageKey.SPLIT, String(this.#share));
    } catch {
      // Storage refused (private window, blocked site data): the share lasts this page.
    }
  }

  /**
   * @param {number} share The share in percent.
   */
  #apply(share) {
    this.#share = Math.min(SIDE_SHARE.MOST, Math.max(SIDE_SHARE.LEAST, share));
    this.#split.style.setProperty('--side-share', `${this.#share}%`);
  }

  /**
   * @param {PointerEvent} event The pointer going down on the divider.
   */
  #startDragging(event) {
    event.preventDefault();
    this.#divider.setPointerCapture?.(event.pointerId);
    this.#divider.classList.add('dragging');
    const bounds = this.#split.getBoundingClientRect();
    const move = (moving) => this.#apply(((bounds.right - moving.clientX) / bounds.width) * 100);
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
      const stored = Number.parseFloat(this.#storage?.getItem(PageStorageKey.SPLIT) ?? '');
      return Number.isFinite(stored) ? stored : null;
    } catch {
      return null;
    }
  }
}
