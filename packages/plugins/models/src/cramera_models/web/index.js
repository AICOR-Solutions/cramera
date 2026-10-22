/**
 * The models plugin's browser module: adds the Models side panel.
 */

import { ModelsClient } from './models-client.js';
import { ModelsPanel } from './models-panel.js';
import { PlotlyLoader } from './plotly-loader.js';

/**
 * The panel's stylesheet, next to this module.
 */
const STYLESHEET = new URL('./models.css', import.meta.url).href;

/**
 * The vendored Plotly bundle, next to this module.
 */
const PLOTLY_BUNDLE = new URL('./vendor/plotly.js-basic-dist-min/plotly-basic.min.js', import.meta.url).href;

// %% registration

/**
 * Add the panel's stylesheet to the page once.
 * @param {Document} document The page.
 */
export function addStylesheet(document) {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = STYLESHEET;
  document.head.append(link);
}

/**
 * Add the Models panel and show what the workbench holds; the viewer does not wait for
 * the workbench to answer.
 * @param {import('../../app/plugin-modules.js').PluginContext} context What the viewer offers plugins.
 * @param {Document=} document The page.
 * @returns {ModelsPanel} The panel.
 */
export function register(context, document = globalThis.document) {
  addStylesheet(document);
  const client = new ModelsClient((url, init) => globalThis.fetch(url, init), context.api);
  const panel = new ModelsPanel(document, client, new PlotlyLoader(document, PLOTLY_BUNDLE));
  context.panels.add(panel.panel);
  panel.refresh();
  return panel;
}
