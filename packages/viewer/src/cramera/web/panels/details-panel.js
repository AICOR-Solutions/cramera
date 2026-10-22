/**
 * What the shown scene is: its names, models, frames and anything that failed to load.
 */

import { ModelKey, RobotKey, SceneKey } from '../protocol.js';
import { SidePanel } from './panel-host.js';

// %% panel

export class DetailsPanel {
  /**
   * The panel.
   * @type {SidePanel}
   */
  panel;

  /**
   * @param {Document} document The page.
   */
  constructor(document) {
    this.panel = new SidePanel('details', 'Details', document.createElement('section'));
  }

  /**
   * @param {import('../scene/scene-loader.js').LoadedScene} scene The shown scene.
   */
  show(scene) {
    const description = scene.description;
    const facts = [
      ['Scene', scene.name],
      ['Task', description[SceneKey.TASK]],
      ['Robot', description[SceneKey.ROBOT_NAME] ?? description[SceneKey.ROBOT]?.[RobotKey.NAME]],
      ['Environment', description[SceneKey.ENVIRONMENT_NAME]],
      ['Models', (description[SceneKey.MODELS] ?? []).map((model) => model[ModelKey.NAME]).join(', ')],
      ['Objects', String((description[SceneKey.OBJECTS] ?? []).length)],
      ['Frames', `${scene.frames.frameCount} at ${scene.frames.framesPerSecond} per second`],
      ['Format', description[SceneKey.FORMAT_VERSION] ?? 'unversioned'],
      ['Missing files', [...(description[SceneKey.MISSING_ASSETS] ?? []), ...scene.missingFiles()].join(', ')],
    ].filter(([, value]) => value);
    const document = this.panel.element.ownerDocument;
    const list = document.createElement('dl');
    list.className = 'facts';
    for (const [term, value] of facts) {
      const name = document.createElement('dt');
      name.textContent = term;
      const content = document.createElement('dd');
      content.textContent = value;
      list.append(name, content);
    }
    this.panel.element.replaceChildren(list);
  }
}
