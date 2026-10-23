/**
 * The browser modules of the viewer's plugins: imported from the URLs the viewer's
 * information lists, each given the same context the built-in parts use.
 */

import { PluginKey, ViewerInfoKey } from '../protocol.js';

// %% context

/**
 * What a plugin module receives: the event bus, the side panels, the viewer's routes,
 * the 3D view, the query slot and the viewer's information.
 */
export class PluginContext {
  /**
   * @param {import('../core/event-bus.js').EventBus} bus The application's event bus.
   * @param {import('../panels/panel-host.js').PanelHost} panels The side panels.
   * @param {import('../core/viewer-api.js').ViewerApi} api The viewer's routes.
   * @param {import('../scene/scene-view.js').SceneView} view The 3D view.
   * @param {import('../panels/query-slot.js').QuerySlot} query The slot above the side
   *   panels one plugin may fill with its question panel.
   * @param {Object} info The viewer's information, which says how it is served.
   */
  constructor(bus, panels, api, view, query, info) {
    /**
     * The application's event bus.
     * @type {import('../core/event-bus.js').EventBus}
     */
    this.bus = bus;
    /**
     * The side panels.
     * @type {import('../panels/panel-host.js').PanelHost}
     */
    this.panels = panels;
    /**
     * The viewer's routes.
     * @type {import('../core/viewer-api.js').ViewerApi}
     */
    this.api = api;
    /**
     * The 3D view.
     * @type {import('../scene/scene-view.js').SceneView}
     */
    this.view = view;
    /**
     * The slot above the side panels one plugin may fill with its question panel.
     * @type {import('../panels/query-slot.js').QuerySlot}
     */
    this.query = query;
    /**
     * The viewer's information.
     * @type {Object}
     */
    this.info = info;
  }

  /**
   * @returns {PluginContext} The context of a plugin the top bar links to: its panels
   *   have no tab, as the top bar shows them.
   */
  withoutTabs() {
    return new PluginContext(this.bus, this.panels.withoutTabs(), this.api, this.view, this.query, this.info);
  }
}

// %% loading

/**
 * A plugin module that exports no `register` function.
 */
export class PluginWithoutRegistration extends Error {
  /**
   * @param {string} name The plugin's name.
   */
  constructor(name) {
    super(`The browser module of plugin ${name} exports no register function.`);
    /**
     * The plugin's name.
     * @type {string}
     */
    this.name = name;
  }
}

export class PluginModules {
  /**
   * Imports a module by URL; the browser's dynamic `import`.
   * @type {function(string): Promise<Object>}
   */
  #importModule;

  /**
   * @param {function(string): Promise<Object>} importModule Imports a module by URL.
   */
  constructor(importModule) {
    this.#importModule = importModule;
  }

  /**
   * Import and register every plugin module: first those of plugins without a
   * navigation entry, which add to the scene page only, then those the header links
   * to, whose panels get no tab; each group in the order the viewer lists them.
   * @param {Object} info The viewer's information.
   * @param {PluginContext} context What each module receives.
   * @param {function(string): string} resolve The absolute URL of a module path.
   * @returns {Promise<Array<string>>} The names of the registered plugins.
   * @throws {PluginWithoutRegistration} When a module exports no `register` function.
   */
  async register(info, context, resolve) {
    const registered = [];
    const plugins = info[ViewerInfoKey.PLUGINS] ?? [];
    const ordered = [...plugins.filter((plugin) => !plugin[PluginKey.NAVIGATION]), ...plugins.filter((plugin) => plugin[PluginKey.NAVIGATION])];
    for (const plugin of ordered) {
      const module = plugin[PluginKey.MODULE];
      if (!module) continue;
      const imported = await this.#importModule(resolve(module));
      if (typeof imported.register !== 'function') throw new PluginWithoutRegistration(plugin[PluginKey.NAME]);
      await imported.register(plugin[PluginKey.NAVIGATION] ? context.withoutTabs() : context);
      registered.push(plugin[PluginKey.NAME]);
    }
    return registered;
  }
}
