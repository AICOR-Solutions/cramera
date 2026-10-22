/**
 * The scene builder's module in the viewer: a side panel that opens the builder page,
 * on its own or on the scene the viewer shows.
 */

import { BuilderPageParameter, SceneBuilderFile, SceneBuilderName, ViewerEvent } from '../../protocol.js';
import { SidePanel } from '../../panels/panel-host.js';

/**
 * The panel's tab text.
 */
export const PANEL_TITLE = 'Scene builder';

/**
 * The colour of the panel's links: the viewer's accent, so they follow its theme.
 */
const LINK_COLOR = 'var(--accent)';

/**
 * How the builder page opens: in a new window that cannot reach the viewer.
 */
const NewWindow = Object.freeze({ TARGET: '_blank', RELATION: 'noopener' });

// %% panel

export class SceneBuilderPanel {
  /**
   * The builder page's URL.
   * @type {string}
   */
  #pageUrl;

  /**
   * The link starting a draft from the shown scene.
   * @type {HTMLAnchorElement}
   */
  #sceneLink;

  /**
   * The paragraph holding that link, hidden until a scene is shown.
   * @type {HTMLParagraphElement}
   */
  #sceneLine;

  /**
   * Removes the panel's subscription again.
   * @type {function(): void}
   */
  #unsubscribe = () => {};

  /**
   * The panel's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * @param {Document} document The viewer's document.
   * @param {string} pageUrl The builder page's URL.
   */
  constructor(document, pageUrl) {
    this.#pageUrl = pageUrl;
    this.element = document.createElement('section');
    const heading = document.createElement('h2');
    heading.textContent = PANEL_TITLE;
    const about = document.createElement('p');
    about.className = 'empty';
    about.textContent = 'Arrange copies of models, robots and scanned rooms into a scene draft. The recordings and models themselves stay unchanged.';
    const open = this.#link(document, 'Open the scene builder');
    open.href = pageUrl;
    const openLine = document.createElement('p');
    openLine.append(open);
    this.#sceneLink = this.#link(document, '');
    this.#sceneLine = document.createElement('p');
    this.#sceneLine.append(this.#sceneLink);
    this.#sceneLine.hidden = true;
    this.element.append(heading, about, openLine, this.#sceneLine);
  }

  /**
   * @param {string} scene The name of the scene the viewer shows.
   */
  showScene(scene) {
    const url = new URL(this.#pageUrl);
    url.searchParams.set(BuilderPageParameter.SCENE, scene);
    this.#sceneLink.href = url.href;
    this.#sceneLink.textContent = `Start a draft from ${scene}`;
    this.#sceneLine.hidden = false;
  }

  /**
   * Follow the scene the viewer shows.
   * @param {import('../../core/event-bus.js').EventBus} bus The viewer's event bus.
   */
  connect(bus) {
    this.#unsubscribe();
    this.#unsubscribe = bus.subscribe(ViewerEvent.SCENE_LOADING, (scene) => this.showScene(scene));
  }

  /**
   * Stop following the shown scene.
   */
  dispose() {
    this.#unsubscribe();
    this.#unsubscribe = () => {};
  }

  /**
   * @param {Document} document The viewer's document.
   * @param {string} text The link's text.
   * @returns {HTMLAnchorElement} A link opening in a new window.
   */
  #link(document, text) {
    const link = document.createElement('a');
    link.textContent = text;
    link.style.color = LINK_COLOR;
    link.target = NewWindow.TARGET;
    link.rel = NewWindow.RELATION;
    return link;
  }
}

// %% registration

/**
 * Add the scene builder's panel to the viewer.
 * @param {import('../../app/plugin-modules.js').PluginContext} context What the viewer offers.
 * @param {Document=} document The viewer's document.
 * @param {string=} pageUrl The builder page's URL.
 * @returns {SceneBuilderPanel} The panel.
 */
export function register(context, document = globalThis.document, pageUrl = new URL(SceneBuilderFile.PAGE, import.meta.url).href) {
  const panel = new SceneBuilderPanel(document, pageUrl);
  panel.connect(context.bus);
  context.panels.add(new SidePanel(SceneBuilderName.PLUGIN, PANEL_TITLE, panel.element));
  return panel;
}
