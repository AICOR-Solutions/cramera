/**
 * What the shown scene is: its names, models, frames and anything that failed to load.
 */

import { ModelKey, RobotKey, SceneKey, SelectionKey, SelectionKind } from '../protocol.js';
import { SidePanel } from './panel-host.js';

// %% panel

export class DetailsPanel {
  /**
   * The panel.
   * @type {SidePanel}
   */
  panel;

  /**
   * The facts about the scene.
   * @type {HTMLElement}
   */
  #sceneFacts;

  /**
   * The facts about the selection.
   * @type {HTMLElement}
   */
  #selectionFacts;

  /**
   * @param {Document} document The page.
   */
  constructor(document) {
    this.panel = new SidePanel('details', 'Details', document.createElement('section'));
    this.#sceneFacts = document.createElement('div');
    this.#selectionFacts = document.createElement('div');
    this.panel.element.append(this.#selectionFacts, this.#sceneFacts);
  }

  /**
   * @param {Object|null} selection The selected link or object, or null.
   */
  showSelection(selection) {
    if (!selection) {
      this.#selectionFacts.replaceChildren();
      return;
    }
    const facts = selection[SelectionKey.KIND] === SelectionKind.LINK
      ? [['Link', selection[SelectionKey.NAME]], ['Model', selection[SelectionKey.MODEL]]]
      : [['Object', selection[SelectionKey.NAME]]];
    this.#selectionFacts.replaceChildren(this.#heading('Selected'), this.#list(facts));
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
    this.#sceneFacts.replaceChildren(this.#heading('Scene'), this.#list(facts));
  }

  /**
   * @param {string} text A section title.
   * @returns {HTMLElement} The heading.
   */
  #heading(text) {
    const heading = this.panel.element.ownerDocument.createElement('h2');
    heading.textContent = text;
    return heading;
  }

  /**
   * @param {Array<Array<string>>} facts Terms and their values.
   * @returns {HTMLElement} The facts as a description list.
   */
  #list(facts) {
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
    return list;
  }
}
