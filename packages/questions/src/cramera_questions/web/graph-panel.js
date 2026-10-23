/**
 * One graph tab: the plan, statechart or kinematics graph of the shown
 * scene; clicking a node lights it up in the 3D view.
 */

import { GraphViewKey, GraphViewName, ViewerEvent } from '../../protocol.js';
import { GraphView } from './graph-view.js';

/**
 * The titles of the views, in the order their tabs are offered.
 */
export const VIEW_TITLES = Object.freeze({
  [GraphViewName.PLAN]: 'Plan',
  [GraphViewName.STATECHART]: 'Statechart',
  [GraphViewName.KINEMATICS]: 'Kinematics',
});

// %% panel

export class GraphPanel {
  /**
   * The panel's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * The `GraphViewName` value the panel draws.
   * @type {string}
   */
  view;

  /**
   * The drawn graph.
   * @type {GraphView}
   */
  #graph;

  /**
   * What the panel says instead of a graph.
   * @type {HTMLElement}
   */
  #message;

  /**
   * Cancels loading a view of a scene that was replaced.
   * @type {AbortController|null}
   */
  #loading = null;

  /**
   * @param {Document} document The page.
   * @param {string} view The `GraphViewName` value the panel draws.
   * @param {import('../../core/event-bus.js').EventBus} bus The application's event bus.
   */
  constructor(document, view, bus) {
    this.view = view;
    this.element = document.createElement('section');
    this.element.className = 'graph-panel';
    this.#message = document.createElement('p');
    this.#message.className = 'graph-empty';
    this.#graph = new GraphView(document, (identity) => bus.publish(ViewerEvent.ENTITY_HIGHLIGHTED, [identity]));
    this.element.append(this.#graph.element, this.#message);
  }

  /**
   * Draw the panel's view of a scene.
   * @param {string} scene The shown bundle.
   * @param {Object} client Where the scene's questions are answered.
   * @returns {Promise<void>} Settles once drawn or failed.
   */
  async showScene(scene, client) {
    this.#loading?.abort();
    const loading = new AbortController();
    this.#loading = loading;
    this.#message.textContent = 'Loading…';
    this.#message.hidden = false;
    const graph = await client.graph(scene, this.view, loading.signal).catch((error) => (loading.signal.aborted ? null : { [GraphViewKey.OK]: false, [GraphViewKey.ERROR]: error.message }));
    if (!graph || loading.signal.aborted) return;
    const nodes = graph[GraphViewKey.NODES] ?? [];
    this.#graph.clear();
    if (graph[GraphViewKey.OK] === false) this.#message.textContent = graph[GraphViewKey.ERROR];
    else if (nodes.length === 0) this.#message.textContent = graph[GraphViewKey.EMPTY] ?? 'This view is empty for the scene.';
    else {
      this.#message.hidden = true;
      this.#graph.show(graph);
    }
  }
}
