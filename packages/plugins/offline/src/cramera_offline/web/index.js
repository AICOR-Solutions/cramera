/**
 * The offline plugin's browser module: adds the Tour panel and, when a scenes
 * directory holds a storyboard, the tour through it.
 */

import { OfflineClient } from './offline-client.js';
import { BrowserTimer, Tour } from './tour.js';
import { TourPanel } from './tour-panel.js';

/**
 * The panel's stylesheet, next to this module.
 */
const STYLESHEET = new URL('./offline.css', import.meta.url).href;

// %% registration

/**
 * Add the Tour panel and read the storyboard; the tour subscribes before the viewer
 * shows its first scene, so the first chapter starts with it.
 * @param {import('../../app/plugin-modules.js').PluginContext} context What the viewer offers plugins.
 * @param {Document=} document The page.
 * @param {BrowserTimer=} timer Calls back after a chapter's time.
 * @returns {Promise<TourPanel>} The panel, once the storyboard is shown.
 */
export async function register(context, document = globalThis.document, timer = new BrowserTimer()) {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = STYLESHEET;
  document.head.append(link);
  const client = new OfflineClient((url) => globalThis.fetch(url), context.api);
  const panel = new TourPanel(document, client, context.bus);
  context.panels.add(panel.panel);
  const answer = await client.storyboard();
  if (answer.problem) {
    panel.showMessage(`The storyboard cannot be read: ${answer.problem}`, true);
    return panel;
  }
  if (!answer.storyboard) {
    panel.showMessage('No storyboard in the scenes directories.', false);
    return panel;
  }
  const tour = new Tour(answer.storyboard, context.bus, context.panels, timer, () => panel.update());
  panel.showTour(tour);
  context.panels.show(panel.panel.identifier);
  return panel;
}
