/**
 * The Graph panel: the knowledge, plan, statechart or kinematics graph of the shown
 * scene; clicking a node lights it up in the 3D view.
 */

import { GraphViewKey, GraphViewName, ViewerEvent } from '../../protocol.js';
import { GraphView } from './graph-view.js';

/**
 * The titles of the views, in the order they are offered.
 */
export const VIEW_TITLES = Object.freeze({
  [GraphViewName.KNOWLEDGE]: 'Knowledge',
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
   * The plugin's routes.
   * @type {import('./questions-client.js').QuestionsClient}
   */
  #client;

  /**
   * The view chooser.
   * @type {HTMLSelectElement}
   */
  #chooser;

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
   * The shown bundle.
   * @type {string|null}
   */
  #scene = null;

  /**
   * The chosen `GraphViewName` value.
   * @type {string}
   */
  #view = GraphViewName.KNOWLEDGE;

  /**
   * Cancels loading a view that was replaced.
   * @type {AbortController|null}
   */
  #loading = null;

  /**
   * @param {Document} document The page.
   * @param {import('./questions-client.js').QuestionsClient} client The plugin's routes.
   * @param {import('../../core/event-bus.js').EventBus} bus The application's event bus.
   */
  constructor(document, client, bus) {
    this.#client = client;
    this.element = document.createElement('section');
    this.element.className = 'graph-panel';
    this.#chooser = document.createElement('select');
    this.#chooser.setAttribute('aria-label', 'Graph');
    for (const [view, title] of Object.entries(VIEW_TITLES)) {
      const option = document.createElement('option');
      option.value = view;
      option.textContent = title;
      this.#chooser.append(option);
    }
    this.#chooser.addEventListener('change', () => this.showView(this.#chooser.value));
    this.#message = document.createElement('p');
    this.#message.className = 'empty';
    this.#graph = new GraphView(document, (identity) => bus.publish(ViewerEvent.ENTITY_HIGHLIGHTED, [identity]));
    this.element.append(this.#chooser, this.#message, this.#graph.element);
  }

  /**
   * @param {string} scene The shown bundle.
   * @returns {Promise<void>} Settles once the chosen view is drawn or has failed.
   */
  showScene(scene) {
    this.#scene = scene;
    return this.showView(this.#view);
  }

  /**
   * @param {string} view A `GraphViewName` value.
   * @returns {Promise<void>} Settles once drawn or failed.
   */
  async showView(view) {
    this.#view = view;
    this.#chooser.value = view;
    if (!this.#scene) return;
    this.#loading?.abort();
    const loading = new AbortController();
    this.#loading = loading;
    this.#message.textContent = 'Loading…';
    const graph = await this.#client.graph(this.#scene, view, loading.signal).catch((error) => (loading.signal.aborted ? null : { [GraphViewKey.OK]: false, [GraphViewKey.ERROR]: error.message }));
    if (!graph || loading.signal.aborted) return;
    const nodes = graph[GraphViewKey.NODES] ?? [];
    this.#graph.clear();
    this.#graph.element.hidden = graph[GraphViewKey.OK] === false || nodes.length === 0;
    if (graph[GraphViewKey.OK] === false) this.#message.textContent = graph[GraphViewKey.ERROR];
    else if (nodes.length === 0) this.#message.textContent = graph[GraphViewKey.EMPTY] ?? 'This view is empty for the scene.';
    else {
      this.#message.textContent = '';
      this.#graph.show(graph);
    }
  }
}
