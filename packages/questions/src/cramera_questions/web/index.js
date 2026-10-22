/**
 * The questions plugin's browser module: adds the Questions panel.
 */

import { PluginName, ViewerEvent } from '../../protocol.js';
import { SidePanel } from '../../panels/panel-host.js';
import { QuestionsClient } from './questions-client.js';
import { QuestionsPanel } from './questions-panel.js';

/**
 * The style sheet of the panel, next to this module.
 */
const STYLE_SHEET = new URL('questions.css', import.meta.url).href;

// %% registration

/**
 * @param {import('../../app/plugin-modules.js').PluginContext} context What the viewer offers.
 * @returns {QuestionsPanel} The panel.
 */
export function register(context) {
  const document = context.view.renderer.domElement.ownerDocument;
  const style = document.createElement('link');
  style.rel = 'stylesheet';
  style.href = STYLE_SHEET;
  document.head.append(style);
  const panel = new QuestionsPanel(document, new QuestionsClient(context.api), context.bus);
  context.panels.add(new SidePanel(PluginName.QUESTIONS, 'Questions', panel.element));
  context.bus.subscribe(ViewerEvent.SCENE_LOADED, (scene) => panel.showScene(scene.name));
  return panel;
}
