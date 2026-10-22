/**
 * The steps of a recorded run, in order; the current step is marked and a click on a
 * step jumps to its start.
 */

import { SegmentKey } from '../protocol.js';
import { SidePanel } from './panel-host.js';

// %% panel

export class StepsPanel {
  /**
   * The panel.
   * @type {SidePanel}
   */
  panel;

  /**
   * The step buttons, in order.
   * @type {Array<HTMLButtonElement>}
   */
  #buttons = [];

  /**
   * Called with the frame a person jumps to.
   * @type {function(number): void}
   */
  #onSeek;

  /**
   * @param {Document} document The page.
   * @param {function(number): void} onSeek Called with the frame a person jumps to.
   */
  constructor(document, onSeek) {
    this.#onSeek = onSeek;
    this.panel = new SidePanel('steps', 'Steps', document.createElement('section'));
  }

  /**
   * @param {Array<Object>} segments The recorded steps.
   */
  show(segments) {
    const document = this.panel.element.ownerDocument;
    this.#buttons = segments.map((segment, position) => {
      const button = document.createElement('button');
      button.className = 'step';
      button.textContent = `${position + 1}. ${segment[SegmentKey.STEP]}`;
      button.addEventListener('click', () => this.#onSeek(segment[SegmentKey.START]));
      return button;
    });
    const empty = document.createElement('p');
    empty.className = 'empty';
    empty.textContent = 'This scene has no recorded steps.';
    this.panel.element.replaceChildren(...(this.#buttons.length ? this.#buttons : [empty]));
  }

  /**
   * @param {number} segment The position of the current step, -1 for none.
   */
  mark(segment) {
    this.#buttons.forEach((button, position) => button.classList.toggle('current', position === segment));
  }
}
