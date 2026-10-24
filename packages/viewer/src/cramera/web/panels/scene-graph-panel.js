/**
 * The Scene graph panel: the shown world as a tree to browse, the way the ontology
 * browser shows classes. A node shows what is known about it, the nodes it depends on
 * and the nodes that depend on it, each a click away; choosing a node lights it up in
 * the 3D view, and choosing a part in the 3D view chooses its node.
 */

import { ModelKey, PartKey, RobotKey, SceneKey, SelectionKey, ViewerEvent } from '../protocol.js';
import { FixedNode, KIND_TITLES, SceneGraph } from '../scene/scene-graph.js';
import { SidePanel } from './panel-host.js';

/**
 * The depth down to which the tree starts unfolded.
 */
export const UNFOLDED_DEPTH = 2;

/**
 * The classes the panel's elements carry.
 */
const PanelClass = Object.freeze({
  COUNTS: 'graph-counts',
  FILTER: 'graph-filter',
  TREE: 'graph-tree',
  NODE: 'graph-node',
  TOGGLE: 'graph-toggle',
  TAG: 'kind-tag',
  DETAILS: 'graph-details',
  CHIPS: 'graph-chips',
  EMPTY: 'empty',
});

// %% facts

/**
 * @param {Object} robot A model as urdf-loader built it.
 * @returns {Array<Object>} Its links, each with its parent link and the joint from it.
 */
function linksOf(robot) {
  return Object.entries(robot.links ?? {}).map(([name, link]) => {
    const joint = link.parent?.isURDFJoint ? link.parent : null;
    const parent = joint?.parent?.isURDFLink ? joint.parent.urdfName : null;
    return {
      name,
      parent,
      joint: joint
        ? { name: joint.urdfName, type: joint.jointType, axis: joint.axis?.toArray?.(), lower: Number(joint.limit?.lower), upper: Number(joint.limit?.upper) }
        : null,
    };
  });
}

/**
 * @param {import('../scene/scene-loader.js').LoadedScene} scene A shown scene.
 * @returns {Object} What the scene graph is built from.
 */
export function sceneFactsOf(scene) {
  const description = scene.description;
  const models = (description[SceneKey.MODELS] ?? []).map((model) => {
    const loaded = scene.models.model(model[ModelKey.NAME]);
    return { name: model[ModelKey.NAME], robot: Boolean(model[ModelKey.ROBOT]), urdf: model[ModelKey.URDF], links: loaded ? linksOf(loaded) : [] };
  });
  const parts = (description[SceneKey.ROBOT]?.[RobotKey.PART_ANNOTATIONS] ?? []).map((part) => ({
    name: part[PartKey.NAME],
    role: part[PartKey.ROLE],
    side: part[PartKey.SIDE],
    links: part[PartKey.LINKS] ?? [],
    attachedTo: part[PartKey.ATTACHED_TO] ?? null,
  }));
  return { name: scene.name, models, objects: scene.objects.named(), parts };
}

// %% panel

export class SceneGraphPanel {
  /**
   * The panel.
   * @type {SidePanel}
   */
  panel;

  /**
   * The bus the panel lights entities up on.
   * @type {import('../core/event-bus.js').EventBus}
   */
  #bus;

  /**
   * The graph shown, or null before a scene is.
   * @type {SceneGraph|null}
   */
  graph = null;

  /**
   * The node chosen, or null.
   * @type {string|null}
   */
  chosen = null;

  /**
   * The nodes unfolded in the tree.
   * @type {Set<string>}
   */
  #unfolded = new Set();

  /**
   * The rows the tree shows, by node, to scroll the chosen one into sight.
   * @type {Map<string, HTMLElement>}
   */
  #rows = new Map();

  /**
   * The counts of the graph's nodes.
   * @type {HTMLElement}
   */
  #counts;

  /**
   * The filter of the tree.
   * @type {HTMLInputElement}
   */
  #filter;

  /**
   * The tree.
   * @type {HTMLElement}
   */
  #tree;

  /**
   * The chosen node's details.
   * @type {HTMLElement}
   */
  #details;

  /**
   * @param {Document} document The page.
   * @param {import('../core/event-bus.js').EventBus} bus The bus the panel lights entities
   *   up on.
   */
  constructor(document, bus) {
    this.#bus = bus;
    this.panel = new SidePanel('scene-graph', 'Scene graph', document.createElement('section'));
    this.panel.element.classList.add('scene-graph');
    this.#counts = document.createElement('p');
    this.#counts.className = PanelClass.COUNTS;
    this.#filter = document.createElement('input');
    this.#filter.type = 'search';
    this.#filter.className = PanelClass.FILTER;
    this.#filter.placeholder = 'Filter the scene graph';
    this.#filter.setAttribute('aria-label', 'Filter the scene graph');
    this.#filter.addEventListener('input', () => this.#renderTree());
    this.#tree = document.createElement('ul');
    this.#tree.className = PanelClass.TREE;
    this.#tree.setAttribute('role', 'tree');
    this.#details = document.createElement('div');
    this.#details.className = PanelClass.DETAILS;
    this.panel.element.append(this.#counts, this.#filter, this.#tree, this.#details);
    this.#renderEmpty();
  }

  /**
   * @param {import('../scene/scene-loader.js').LoadedScene} scene The shown scene.
   */
  show(scene) {
    this.showGraph(SceneGraph.of(sceneFactsOf(scene)));
  }

  /**
   * @param {SceneGraph} graph The graph to show, the tree unfolded down to
   *   :data:`UNFOLDED_DEPTH`.
   */
  showGraph(graph) {
    this.graph = graph;
    this.chosen = null;
    this.#unfolded = new Set();
    const unfold = (identifier, depth) => {
      if (depth >= UNFOLDED_DEPTH) return;
      this.#unfolded.add(identifier);
      for (const child of graph.children(identifier)) unfold(child.identifier, depth + 1);
    };
    unfold(FixedNode.WORLD, 0);
    const counts = [...graph.counts()].map(([kind, count]) => `${count} ${KIND_TITLES[kind].toLowerCase()}${count === 1 ? '' : 's'}`);
    this.#counts.textContent = counts.join(' · ');
    this.#renderTree();
    this.#renderDetails();
  }

  /**
   * Choose a node: unfold the tree down to it, show its details and light it up.
   * @param {string} identifier A node's identity.
   */
  choose(identifier) {
    const node = this.graph?.node(identifier);
    if (!node) return;
    this.chosen = identifier;
    for (const ancestor of this.graph.ancestors(identifier)) this.#unfolded.add(ancestor);
    this.#renderTree();
    this.#renderDetails();
    this.#rows.get(identifier)?.scrollIntoView?.({ block: 'nearest' });
    this.#bus.publish(ViewerEvent.ENTITY_HIGHLIGHTED, node.keys);
  }

  /**
   * Choose the node of what the 3D view selected.
   * @param {Object|null} selection The selected link or object, or null.
   */
  reveal(selection) {
    if (!selection || !this.graph) return;
    const identifier = this.graph.nodeOf(selection[SelectionKey.KIND], selection[SelectionKey.NAME], selection[SelectionKey.MODEL]);
    if (identifier) this.choose(identifier);
  }

  /**
   * Show that no scene is shown yet.
   */
  #renderEmpty() {
    const document = this.panel.element.ownerDocument;
    this.#tree.replaceChildren();
    this.#details.replaceChildren(this.#element(document, 'p', PanelClass.EMPTY, 'The scene graph appears once a scene is shown.'));
  }

  /**
   * Show the tree, the filter's matches unfolded and the rest as the person left it.
   */
  #renderTree() {
    if (!this.graph) return;
    const document = this.panel.element.ownerDocument;
    const shown = this.graph.matching(this.#filter.value);
    this.#rows = new Map();
    const branch = (identifier) =>
      this.graph
        .children(identifier)
        .filter((node) => !shown || shown.has(node.identifier))
        .map((node) => this.#item(document, node, shown, branch));
    this.#tree.replaceChildren(...branch(null));
  }

  /**
   * @param {Document} document The page.
   * @param {import('../scene/scene-graph.js').GraphNode} node A node.
   * @param {Set<string>|null} shown The nodes the filter shows, or null for all.
   * @param {function(string): Array<HTMLElement>} branch Builds a node's children.
   * @returns {HTMLElement} The node's item, with its unfolded children.
   */
  #item(document, node, shown, branch) {
    const item = this.#element(document, 'li', PanelClass.NODE);
    item.setAttribute('role', 'treeitem');
    item.dataset.node = node.identifier;
    const children = this.graph.children(node.identifier);
    const unfolded = Boolean(shown) || this.#unfolded.has(node.identifier);
    const toggle = this.#element(document, 'button', PanelClass.TOGGLE, children.length ? (unfolded ? '▾' : '▸') : '·');
    toggle.type = 'button';
    toggle.disabled = !children.length;
    toggle.setAttribute('aria-label', unfolded ? `Fold ${node.label}` : `Unfold ${node.label}`);
    toggle.addEventListener('click', () => {
      if (this.#unfolded.has(node.identifier)) this.#unfolded.delete(node.identifier);
      else this.#unfolded.add(node.identifier);
      this.#renderTree();
    });
    const label = this.#nodeButton(document, node);
    if (children.length) label.append(this.#element(document, 'span', 'count', String(children.length)));
    const row = this.#element(document, 'div', 'graph-row');
    row.append(toggle, label);
    this.#rows.set(node.identifier, row);
    item.append(row);
    item.setAttribute('aria-expanded', String(unfolded));
    if (children.length && unfolded) {
      const list = this.#element(document, 'ul');
      list.setAttribute('role', 'group');
      list.append(...branch(node.identifier));
      item.append(list);
    }
    return item;
  }

  /**
   * Show the chosen node's details: its fields, the nodes it depends on and the nodes
   * depending on it.
   */
  #renderDetails() {
    const document = this.panel.element.ownerDocument;
    const node = this.chosen ? this.graph.node(this.chosen) : null;
    if (!node) {
      this.#details.replaceChildren(this.#element(document, 'p', PanelClass.EMPTY, 'Choose a node to see what it is and what it depends on, or click a part in the 3D view.'));
      return;
    }
    const heading = this.#element(document, 'h3');
    heading.append(this.#tag(document, node.kind), ` ${node.label}`);
    const facts = this.#element(document, 'dl');
    for (const [name, value] of node.fields) facts.append(this.#element(document, 'dt', '', name), this.#element(document, 'dd', '', value));
    const parts = [heading, facts];
    const dependsOn = node.references.map((reference) => ({ field: reference.field, node: this.graph.node(reference.target) })).filter((entry) => entry.node);
    if (dependsOn.length) parts.push(this.#element(document, 'h4', '', 'Depends on'), this.#chips(document, dependsOn));
    const usedBy = this.graph.referencedBy(node.identifier).map((entry) => ({ field: entry.field, node: entry.source }));
    if (usedBy.length) parts.push(this.#element(document, 'h4', '', 'Referenced by'), this.#chips(document, usedBy));
    this.#details.replaceChildren(...parts);
  }

  /**
   * @param {Document} document The page.
   * @param {Array<{field: string, node: Object}>} entries Related nodes and the fields
   *   relating them.
   * @returns {HTMLElement} The nodes as buttons choosing them.
   */
  #chips(document, entries) {
    const list = this.#element(document, 'ul', PanelClass.CHIPS);
    for (const { field, node } of entries) {
      const item = this.#element(document, 'li');
      item.append(this.#element(document, 'span', 'field', field), this.#nodeButton(document, node));
      list.append(item);
    }
    return list;
  }

  /**
   * @param {Document} document The page.
   * @param {import('../scene/scene-graph.js').GraphNode} node A node.
   * @returns {HTMLButtonElement} A button choosing it, with its kind tag.
   */
  #nodeButton(document, node) {
    const button = this.#element(document, 'button', 'graph-label');
    button.type = 'button';
    button.dataset.node = node.identifier;
    if (node.identifier === this.chosen) button.setAttribute('aria-current', 'true');
    button.append(this.#tag(document, node.kind), this.#element(document, 'span', 'name', node.label));
    button.addEventListener('click', () => this.choose(node.identifier));
    return button;
  }

  /**
   * @param {Document} document The page.
   * @param {string} kind A `NodeKind` value.
   * @returns {HTMLElement} The kind's coloured tag.
   */
  #tag(document, kind) {
    const tag = this.#element(document, 'span', PanelClass.TAG, '');
    tag.dataset.kind = kind;
    tag.title = KIND_TITLES[kind];
    return tag;
  }

  /**
   * @param {Document} document The page.
   * @param {string} tag The element's tag.
   * @param {string=} className Its classes.
   * @param {string=} text Its text.
   * @returns {HTMLElement} The element.
   */
  #element(document, tag, className = '', text = '') {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  }
}

