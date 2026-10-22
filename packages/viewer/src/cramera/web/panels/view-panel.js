/**
 * How the 3D view draws the scene: ambient occlusion and the ground's shadows.
 */

import { SidePanel } from './panel-host.js';

// %% panel

/**
 * One switch of the panel.
 */
export class ViewSwitch {
  /**
   * @param {string} label What the switch changes.
   * @param {function(): boolean} read Whether it is on now.
   * @param {function(boolean): void} write Turns it on or off.
   */
  constructor(label, read, write) {
    /**
     * What the switch changes.
     * @type {string}
     */
    this.label = label;
    /**
     * Whether it is on now.
     * @type {function(): boolean}
     */
    this.read = read;
    /**
     * Turns it on or off.
     * @type {function(boolean): void}
     */
    this.write = write;
  }
}

export class ViewPanel {
  /**
   * The panel.
   * @type {SidePanel}
   */
  panel;

  /**
   * The switches with their checkboxes.
   * @type {Array<{viewSwitch: ViewSwitch, input: HTMLInputElement}>}
   */
  #switches = [];

  /**
   * @param {Document} document The page.
   * @param {Array<ViewSwitch>} switches The switches to offer.
   */
  constructor(document, switches) {
    this.panel = new SidePanel('view', 'View', document.createElement('section'));
    for (const viewSwitch of switches) {
      const label = document.createElement('label');
      label.className = 'switch';
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.addEventListener('change', () => viewSwitch.write(input.checked));
      const text = document.createElement('span');
      text.textContent = viewSwitch.label;
      label.append(input, text);
      this.panel.element.append(label);
      this.#switches.push({ viewSwitch, input });
    }
    this.refresh();
  }

  /**
   * Show each switch's current state, after a scene set its own.
   */
  refresh() {
    for (const { viewSwitch, input } of this.#switches) input.checked = viewSwitch.read();
  }
}
