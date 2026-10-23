/**
 * The questions plugin's browser module: fills the viewer's query slot with the
 * question panel and adds one tab per graph view. Where the plugin's routes do not
 * answer, as on a static site, both show the scene's recorded answers.
 */

import { PluginName, Serving, ViewerEvent, ViewerInfoKey } from '../../protocol.js';
import { SidePanel } from '../../panels/panel-host.js';
import { SlotPanel } from '../../panels/query-slot.js';
import { GraphPanel, VIEW_TITLES } from './graph-panel.js';
import { QuestionsClient } from './questions-client.js';
import { QuestionsPanel } from './questions-panel.js';
import { AnswerSources, RecordedAnswersClient } from './recorded-answers.js';

/**
 * The style sheet of the panels, next to this module.
 */
const STYLE_SHEET = new URL('questions.css', import.meta.url).href;

/**
 * The heading of the question panel.
 */
export const PANEL_TITLE = 'EQL · entity query language';

/**
 * @param {string} view A `GraphViewName` value.
 * @returns {string} The identity of the view's tab.
 */
export function graphPanelOf(view) {
  return `${PluginName.QUESTIONS}-${view}`;
}

// %% registration

/**
 * @param {import('../../app/plugin-modules.js').PluginContext} context What the viewer offers.
 * @returns {QuestionsPanel} The question panel.
 */
export function register(context) {
  const document = context.view.renderer.domElement.ownerDocument;
  const style = document.createElement('link');
  style.rel = 'stylesheet';
  style.href = STYLE_SHEET;
  document.head.append(style);
  const served = context.info?.[ViewerInfoKey.SERVING] !== Serving.STATIC;
  const sources = new AnswerSources(served ? new QuestionsClient(context.api) : null, new RecordedAnswersClient(context.api));
  const panel = new QuestionsPanel(document, context.bus);
  context.query.fill(new SlotPanel(PluginName.QUESTIONS, PANEL_TITLE, panel.element, panel.status));
  const graphs = Object.entries(VIEW_TITLES).map(([view, title]) => {
    const graph = new GraphPanel(document, view, context.bus);
    context.panels.add(new SidePanel(graphPanelOf(view), title, graph.element));
    return graph;
  });
  let loading = null;
  context.bus.subscribe(ViewerEvent.SCENE_LOADED, async (scene) => {
    loading?.abort();
    loading = new AbortController();
    const signal = loading.signal;
    const source = await sources.forScene(scene.name, signal);
    if (signal.aborted) return;
    panel.showScene(scene.name, source);
    for (const graph of graphs) graph.showScene(scene.name, source.client);
  });
  return panel;
}
