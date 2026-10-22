/**
 * The workshop plugin's browser module: the Workshop side panel. On a workshop scene it
 * starts the contact world and shows what MuJoCo measures; on a recording made in the
 * workshop it shows the assets' rights.
 */

import {
  IndexEntryKey,
  IndexKey,
  SelectionKey,
  SelectionKind,
  ViewerEvent,
  WorkshopKey,
  WorkshopSceneKey,
} from '../../protocol.js';
import { SidePanel } from '../../panels/panel-host.js';
import { WorkshopClient } from './workshop-client.js';
import { Manipulation, WorkshopController } from './workshop-controller.js';
import { WorkshopPanel, rightsElement } from './workshop-panel.js';
import { WorkshopScene } from './workshop-scene.js';

/**
 * The panel's identity and tab text.
 */
export const PANEL = Object.freeze({ IDENTIFIER: 'workshop', TITLE: 'Workshop' });

/**
 * The panel's stylesheet, next to this module.
 */
const STYLESHEET = new URL('./workshop.css', import.meta.url).href;

/**
 * What the panel says on a scene without a workshop.
 */
export const IDLE_TEXT = 'Open the AICOR workshop scene to start its MuJoCo contact world.';

// %% module

/**
 * The browser's timers; `globalThis` in the browser, replaced in tests.
 * @typedef {{setInterval: function(function(): void, number): number, clearInterval: function(number): void}} Timers
 */

export class WorkshopModule {
  /**
   * What the viewer offers the plugin.
   * @type {import('../../app/plugin-modules.js').PluginContext}
   */
  #context;

  /**
   * The page.
   * @type {Document}
   */
  #document;

  /**
   * The browser's timers.
   * @type {Timers}
   */
  #timers;

  /**
   * The workshop routes.
   * @type {WorkshopClient}
   */
  #client;

  /**
   * The polling timer of the shown workshop, or null.
   * @type {number|null}
   */
  #timer = null;

  /**
   * The side panel.
   * @type {SidePanel}
   */
  panel;

  /**
   * The commands of the shown workshop, or null on another scene.
   * @type {WorkshopController|null}
   */
  controller = null;

  /**
   * The content shown for a workshop scene, or null.
   * @type {WorkshopPanel|null}
   */
  content = null;

  /**
   * @param {import('../../app/plugin-modules.js').PluginContext} context What the viewer offers the plugin.
   * @param {Document} document The page.
   * @param {Timers} timers The browser's timers.
   * @param {WorkshopClient} client The workshop routes.
   */
  constructor(context, document, timers, client) {
    this.#context = context;
    this.#document = document;
    this.#timers = timers;
    this.#client = client;
    const section = document.createElement('section');
    section.className = 'workshop-module';
    this.panel = new SidePanel(PANEL.IDENTIFIER, PANEL.TITLE, section);
    this.#showIdle();
    context.bus.subscribe(ViewerEvent.SCENE_LOADING, () => this.leave());
    context.bus.subscribe(ViewerEvent.SCENE_LOADED, (loaded) => this.enter(loaded));
    context.bus.subscribe(ViewerEvent.ENTITY_SELECTED, (selection) => this.select(selection));
  }

  /**
   * Show the contact world of a workshop scene, or the rights of a recording made in one.
   * @param {import('../../scene/scene-loader.js').LoadedScene} loaded The shown scene.
   * @returns {Promise<void>} Settles once the recorded demo's availability is known.
   */
  async enter(loaded) {
    const description = loaded.description;
    const workshop = description[WorkshopSceneKey.WORKSHOP];
    const rights = description[WorkshopSceneKey.ASSET_RIGHTS] ?? null;
    if (!workshop) {
      if (rights) this.#showRights(rights);
      return;
    }
    const scene = new WorkshopScene(loaded, this.#context.view, this.#context.bus);
    this.controller = new WorkshopController(workshop, scene, this.#client);
    const demoScene = workshop[WorkshopKey.DEMO_SCENE];
    this.content = new WorkshopPanel(this.#document, workshop, this.controller, rights, () =>
      this.#context.bus.publish(ViewerEvent.SCENE_REQUESTED, demoScene),
    );
    this.panel.element.replaceChildren(this.content.element);
    this.#timer = this.#timers.setInterval(() => this.controller.poll(), Manipulation.POLL_MILLISECONDS);
    this.controller.start();
    if (demoScene) await this.#offerDemo(demoScene, this.content);
  }

  /**
   * Stop showing the workshop, before another scene loads.
   * @returns {Promise<void>} Settles once a held body was let go.
   */
  leave() {
    if (this.#timer !== null) this.#timers.clearInterval(this.#timer);
    this.#timer = null;
    const controller = this.controller;
    this.controller = null;
    this.content = null;
    this.#showIdle();
    return controller ? controller.close().then(() => undefined) : Promise.resolve();
  }

  /**
   * Make a body picked in the 3D view the panel's selected one.
   * @param {Object|null} selection The selection, or null.
   */
  select(selection) {
    if (!this.controller || selection?.[SelectionKey.KIND] !== SelectionKind.OBJECT) return;
    this.controller.select(selection[SelectionKey.NAME]);
  }

  /**
   * @param {string} name The recorded demo's bundle.
   * @param {WorkshopPanel} content The content offering it.
   */
  async #offerDemo(name, content) {
    const index = await this.#context.api.scenes().catch(() => ({}));
    const entries = index[IndexKey.SCENES] ?? [];
    content.offerDemo(entries.some((entry) => entry[IndexEntryKey.NAME] === name));
  }

  /**
   * Show what the panel does on a scene without a workshop.
   */
  #showIdle() {
    const text = this.#document.createElement('p');
    text.className = 'workshop-note';
    text.textContent = IDLE_TEXT;
    this.panel.element.replaceChildren(text);
  }

  /**
   * @param {Object} rights The asset rights of the shown recording.
   */
  #showRights(rights) {
    this.panel.element.replaceChildren(rightsElement(this.#document, rights));
  }
}

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
 * Add the Workshop panel; it follows the scenes the viewer shows.
 * @param {import('../../app/plugin-modules.js').PluginContext} context What the viewer offers plugins.
 * @param {Document=} document The page.
 * @param {Timers=} timers The browser's timers.
 * @returns {WorkshopModule} The module.
 */
export function register(context, document = globalThis.document, timers = globalThis) {
  addStylesheet(document);
  const client = new WorkshopClient((url, init) => globalThis.fetch(url, init), context.api);
  const module = new WorkshopModule(context, document, timers, client);
  context.panels.add(module.panel);
  return module;
}
