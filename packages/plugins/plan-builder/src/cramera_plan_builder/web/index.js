/**
 * The plan view in the viewer: a side panel that shows the plan of a replayed recording
 * as the builder's step cards, with every parameter and constraint each step was
 * recorded with, following the playhead.
 */

import { PlanBuilderFile, PlanBuilderName, SceneKey, ViewerEvent } from '../../protocol.js';
import { SidePanel } from '../../panels/panel-host.js';
import { RecordedPlanView } from './builder/recorded-plan-view.js';

/**
 * The panel's tab text.
 */
export const PANEL_TITLE = 'Plan View';

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
   */
  constructor(document) {
    this.element = document.createElement('section');
    const heading = document.createElement('h2');
    heading.textContent = PANEL_TITLE;
    this.#recorded = new RecordedPlanView(document, (frame) => this.#requestFrame(frame));
    this.element.append(heading, this.#recorded.element);
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
}

// %% registration

/**
 * Add the plan view's panel and the step cards' stylesheet to the viewer.
 * @param {import('../../app/plugin-modules.js').PluginContext} context What the viewer offers.
 * @param {Document=} document The viewer's document.
 * @returns {PlanBuilderPanel} The panel.
 */
export function register(context, document = globalThis.document) {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = STEPS_STYLESHEET;
  document.head.append(link);
  const panel = new PlanBuilderPanel(document);
  panel.connect(context.bus, context.panels);
  context.panels.add(new SidePanel(PlanBuilderName.PLUGIN, PANEL_TITLE, panel.element));
  return panel;
}
