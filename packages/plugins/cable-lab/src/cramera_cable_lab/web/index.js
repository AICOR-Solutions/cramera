/**
 * The cable lab plugin's module in the viewer: a side panel that opens the cable lab
 * page in a window of its own.
 */

import { CableLabFile, PluginName } from '../../protocol.js';
import { SidePanel } from '../../panels/panel-host.js';

/**
 * The panel's tab text.
 */
export const PANEL_TITLE = 'Cable lab';

/**
 * What the panel says about the lab.
 */
export const PANEL_TEXT = 'Pinch, lift and drop a MuJoCo composite cable with a friction gripper, and read the measured contact forces.';

/**
 * The link's text.
 */
export const LINK_TEXT = 'Open the cable lab';

/**
 * How the lab opens: in a new window that cannot reach the viewer.
 */
const NewWindow = Object.freeze({ TARGET: '_blank', RELATION: 'noopener' });

// %% panel

/**
 * @param {Document} document The viewer's document.
 * @param {string} pageUrl The cable lab page's URL.
 * @returns {HTMLElement} The panel's content.
 */
export function panelContent(document, pageUrl) {
  const element = document.createElement('section');
  const about = document.createElement('p');
  about.className = 'empty';
  about.textContent = PANEL_TEXT;
  const link = document.createElement('a');
  link.textContent = LINK_TEXT;
  link.href = pageUrl;
  link.target = NewWindow.TARGET;
  link.rel = NewWindow.RELATION;
  link.style.color = 'var(--accent)';
  const line = document.createElement('p');
  line.append(link);
  element.append(about, line);
  return element;
}

// %% registration

/**
 * Add the Cable lab panel to the viewer.
 * @param {import('../../app/plugin-modules.js').PluginContext} context What the viewer offers.
 * @param {Document=} document The viewer's document.
 * @param {string=} pageUrl The cable lab page's URL.
 * @returns {SidePanel} The panel.
 */
export function register(context, document = globalThis.document, pageUrl = new URL(CableLabFile.PAGE, import.meta.url).href) {
  const panel = new SidePanel(PluginName.CABLE_LAB, PANEL_TITLE, panelContent(document, pageUrl));
  context.panels.add(panel);
  return panel;
}
