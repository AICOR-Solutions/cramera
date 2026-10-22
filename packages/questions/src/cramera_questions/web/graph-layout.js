/**
 * Placing the nodes of a graph view: a layered tree for hierarchy views, a force
 * layout for free ones. Both are deterministic, so a view looks the same every time.
 */

import { GraphEdgeKey, GraphLayout, GraphNodeKey, GraphViewKey } from '../../protocol.js';

/**
 * The distances of the layouts, in drawing units.
 */
export const Spacing = Object.freeze({ LAYER: 90, SIBLING: 70, EDGE: 80 });

/**
 * How the force layout runs: its rounds, the repulsion between nodes, the pull of
 * edges, and how far one round may move a node.
 */
const Force = Object.freeze({ ROUNDS: 300, REPULSION: 6000, ATTRACTION: 0.02, STEP: 12 });

// %% positions

/**
 * A node's place in the drawing.
 */
export class Placement {
  /**
   * @param {number} x The horizontal coordinate.
   * @param {number} y The vertical coordinate.
   */
  constructor(x, y) {
    /**
     * The horizontal coordinate.
     * @type {number}
     */
    this.x = x;
    /**
     * The vertical coordinate.
     * @type {number}
     */
    this.y = y;
  }
}

/**
 * @param {Object} view A graph view.
 * @returns {Map<string, Placement>} The place of every node, by its identity.
 */
export function placeNodes(view) {
  const nodes = view[GraphViewKey.NODES] ?? [];
  const edges = view[GraphViewKey.EDGES] ?? [];
  const layout = view[GraphViewKey.LAYOUT] ?? GraphLayout.FREE;
  if (layout === GraphLayout.FREE) return forceLayout(nodes, edges);
  const placements = treeLayout(nodes, edges);
  if (layout !== GraphLayout.HIERARCHY_LEFT_RIGHT) return placements;
  return new Map([...placements].map(([identity, place]) => [identity, new Placement(place.y, place.x)]));
}

// %% tree

/**
 * Layers the nodes by their depth below the roots; children follow their parent,
 * leaves are spread evenly, each parent is centred over its children.
 * @param {Array<Object>} nodes The nodes.
 * @param {Array<Object>} edges The edges, from parent to child.
 * @returns {Map<string, Placement>} The places, top-down.
 */
export function treeLayout(nodes, edges) {
  const identities = nodes.map((node) => node[GraphNodeKey.IDENTIFIER]);
  const children = new Map(identities.map((identity) => [identity, []]));
  const hasParent = new Set();
  for (const edge of edges) {
    const parent = edge[GraphEdgeKey.SOURCE];
    const child = edge[GraphEdgeKey.DESTINATION];
    if (!children.has(parent) || !children.has(child) || hasParent.has(child) || parent === child) continue;
    children.get(parent).push(child);
    hasParent.add(child);
  }
  const placements = new Map();
  let nextLeaf = 0;
  const place = (identity, depth) => {
    const below = children.get(identity).filter((child) => !placements.has(child));
    placements.set(identity, null);
    const xs = below.map((child) => place(child, depth + 1));
    const x = xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : nextLeaf++ * Spacing.SIBLING;
    placements.set(identity, new Placement(x, depth * Spacing.LAYER));
    return x;
  };
  for (const identity of identities) if (!hasParent.has(identity) && !placements.has(identity)) place(identity, 0);
  for (const identity of identities) if (!placements.has(identity)) place(identity, 0);
  return placements;
}

// %% force

/**
 * Starts the nodes on a circle and lets every pair repel and every edge pull for a
 * fixed number of rounds.
 * @param {Array<Object>} nodes The nodes.
 * @param {Array<Object>} edges The edges.
 * @returns {Map<string, Placement>} The places.
 */
export function forceLayout(nodes, edges) {
  const identities = nodes.map((node) => node[GraphNodeKey.IDENTIFIER]);
  const radius = Math.max(identities.length * Spacing.EDGE / (2 * Math.PI), Spacing.EDGE);
  const points = identities.map((_, position) => {
    const angle = (2 * Math.PI * position) / Math.max(identities.length, 1);
    return { x: radius * Math.cos(angle), y: radius * Math.sin(angle) };
  });
  const index = new Map(identities.map((identity, position) => [identity, position]));
  const links = edges
    .map((edge) => [index.get(edge[GraphEdgeKey.SOURCE]), index.get(edge[GraphEdgeKey.DESTINATION])])
    .filter(([source, destination]) => source !== undefined && destination !== undefined && source !== destination);
  for (let round = 0; round < Force.ROUNDS; round++) {
    const moves = points.map(() => ({ x: 0, y: 0 }));
    for (let first = 0; first < points.length; first++) {
      for (let second = first + 1; second < points.length; second++) {
        const dx = points[first].x - points[second].x;
        const dy = points[first].y - points[second].y;
        const squared = Math.max(dx * dx + dy * dy, 1);
        const push = Force.REPULSION / squared;
        const distance = Math.sqrt(squared);
        moves[first].x += (dx / distance) * push;
        moves[first].y += (dy / distance) * push;
        moves[second].x -= (dx / distance) * push;
        moves[second].y -= (dy / distance) * push;
      }
    }
    for (const [source, destination] of links) {
      const dx = points[destination].x - points[source].x;
      const dy = points[destination].y - points[source].y;
      const pull = Force.ATTRACTION * (Math.hypot(dx, dy) - Spacing.EDGE);
      const distance = Math.max(Math.hypot(dx, dy), 1);
      moves[source].x += (dx / distance) * pull * Spacing.EDGE;
      moves[source].y += (dy / distance) * pull * Spacing.EDGE;
      moves[destination].x -= (dx / distance) * pull * Spacing.EDGE;
      moves[destination].y -= (dy / distance) * pull * Spacing.EDGE;
    }
    const cooling = 1 - round / Force.ROUNDS;
    points.forEach((point, position) => {
      const length = Math.hypot(moves[position].x, moves[position].y);
      const step = Math.min(length, Force.STEP * cooling);
      if (length > 0) {
        point.x += (moves[position].x / length) * step;
        point.y += (moves[position].y / length) * step;
      }
    });
  }
  return new Map(identities.map((identity, position) => [identity, new Placement(points[position].x, points[position].y)]));
}
