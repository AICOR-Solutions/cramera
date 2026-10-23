/**
 * The plan builder's module in the viewer: a side panel that opens the builder page, on
 * its own or in the environment the viewer shows, and shows the plan of a replayed
 * recording as the builder's step cards, following the playhead.
 */

import { PlanBuilderFile, PlanBuilderName, PlanBuilderPageParameter, SceneKey, ViewerEvent } from '../../protocol.js';
import { SidePanel } from '../../panels/panel-host.js';
import { RecordedPlanView } from './builder/recorded-plan-view.js';

/**
 * The panel's tab text.
 */
export const PANEL_TITLE = 'Plan builder';

/**
 * The colour of the panel's links: the viewer's accent, so they follow its theme.
 */
const LINK_COLOR = 'var(--accent)';

/**
 * How the builder page opens: in a new window that cannot reach the viewer.
 */
const NewWindow = Object.freeze({ TARGET: '_blank', RELATION: 'noopener' });

/**
 * The frame a newly shown recording is at.
 */
const FIRST_FRAME = 0;

/**
 * The stylesheet of the step cards, next to this module.
 */
const STEPS_STYLESHEET = new URL(PlanBuilderFile.STEPS_STYLESHEET, import.meta.url).href;

// %% panel

export class PlanBuilderPanel {
  /**
   * The builder page's URL.
   * @type {string}
   */
  #pageUrl;

  /**
   * The link starting a plan in the shown scene.
   * @type {HTMLAnchorElement}
   */
  #sceneLink;

  /**
   * The paragraph holding that link, hidden until a scene is shown.
   * @type {HTMLParagraphElement}
   */
  #sceneLine;

  /**
   * Removes the panel's subscriptions again.
   * @type {Array<function(): void>}
   */
  #subscriptions = [];

  /**
   * The plan of the replayed recording.
   * @type {RecordedPlanView}
   */
  #recorded;

  /**
   * Asks the viewer for a frame of the recording; does nothing until connected.
   * @type {function(number): void}
   */
  #requestFrame = () => {};

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
    about.textContent = 'Compose a robot plan from actions, place its objects and targets, attach constraints in plain language and run the generated demo.';
    const open = this.#link(document, 'Open the plan builder');
    open.href = pageUrl;
    const openLine = document.createElement('p');
    openLine.append(open);
    this.#sceneLink = this.#link(document, '');
    this.#sceneLine = document.createElement('p');
    this.#sceneLine.append(this.#sceneLink);
    this.#sceneLine.hidden = true;
    this.#recorded = new RecordedPlanView(document, (frame) => this.#requestFrame(frame));
    this.element.append(heading, about, openLine, this.#sceneLine, this.#recorded.element);
  }

  /**
   * @param {string} scene The name of the scene the viewer shows; the page starts a plan
   *   in it when it is an environment.
   */
  showScene(scene) {
    const url = new URL(this.#pageUrl);
    url.searchParams.set(PlanBuilderPageParameter.ENVIRONMENT, scene);
    this.#sceneLink.href = url.href;
    this.#sceneLink.textContent = `Plan in ${scene}`;
    this.#sceneLine.hidden = false;
  }

  /**
   * Show the plan of a loaded scene; the panel comes to the front when the scene is a
   * recording of a plan.
   * @param {Object} scene The loaded scene, with its `description`.
   * @param {function(): void} bringForward Shows this panel.
   */
  showRecording(scene, bringForward) {
    this.#recorded.show(scene.description[SceneKey.PLAN_TREES] ?? []);
    if (!this.#recorded.hasPlan()) return;
    this.#recorded.showFrame(FIRST_FRAME);
    bringForward();
  }

  /**
   * Follow the scene the viewer shows and its playhead.
   * @param {import('../../core/event-bus.js').EventBus} bus The viewer's event bus.
   * @param {import('../../panels/panel-host.js').PanelHost} panels The viewer's side panels.
   */
  connect(bus, panels) {
    this.#unsubscribe();
    this.#requestFrame = (frame) => bus.publish(ViewerEvent.FRAME_REQUESTED, frame);
    this.#subscriptions = [
      bus.subscribe(ViewerEvent.SCENE_LOADING, (scene) => this.showScene(scene)),
      bus.subscribe(ViewerEvent.SCENE_LOADED, (scene) => this.showRecording(scene, () => panels.show(PlanBuilderName.PLUGIN))),
      bus.subscribe(ViewerEvent.FRAME_CHANGED, (frame) => this.#recorded.showFrame(frame)),
    ];
  }

  /**
   * Stop following the shown scene and remove the listeners of the recorded plan.
   */
  dispose() {
    this.#unsubscribe();
    this.#recorded.dispose();
  }

  /**
   * Remove the panel's subscriptions.
   */
  #unsubscribe() {
    for (const unsubscribe of this.#subscriptions) unsubscribe();
    this.#subscriptions = [];
    this.#requestFrame = () => {};
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
 * Add the plan builder's panel and the step cards' stylesheet to the viewer.
 * @param {import('../../app/plugin-modules.js').PluginContext} context What the viewer offers.
 * @param {Document=} document The viewer's document.
 * @param {string=} pageUrl The builder page's URL.
 * @returns {PlanBuilderPanel} The panel.
 */
export function register(context, document = globalThis.document, pageUrl = new URL(PlanBuilderFile.PAGE, import.meta.url).href) {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = STEPS_STYLESHEET;
  document.head.append(link);
  const panel = new PlanBuilderPanel(document, pageUrl);
  panel.connect(context.bus, context.panels);
  context.panels.add(new SidePanel(PlanBuilderName.PLUGIN, PANEL_TITLE, panel.element));
  return panel;
}
