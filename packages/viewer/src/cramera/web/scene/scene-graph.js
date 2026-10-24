/**
 * The scene graph of a shown world: its models with their links nested by the joints
 * that connect them, its free objects, and the robot's part annotations with the links
 * they depend on, as the ontology browser shows classes with the classes their fields
 * refer to.
 *
 * The graph is built from plain facts about the scene, so it does not depend on how the
 * 3D view loaded the models.
 */

// %% nodes

/**
 * What a node of the scene graph stands for.
 */
export const NodeKind = Object.freeze({
  WORLD: 'world',
  MODEL: 'model',
  LINK: 'link',
  GROUP: 'group',
  OBJECT: 'object',
  PART: 'part',
});

/**
 * How people read each kind of node.
 */
export const KIND_TITLES = Object.freeze({
  [NodeKind.WORLD]: 'World',
  [NodeKind.MODEL]: 'Model',
  [NodeKind.LINK]: 'Link',
  [NodeKind.GROUP]: 'Group',
  [NodeKind.OBJECT]: 'Object',
  [NodeKind.PART]: 'Part annotation',
});

/**
 * The identities of the nodes every graph has.
 */
export const FixedNode = Object.freeze({ WORLD: 'world', OBJECTS: 'group:objects', PARTS: 'group:parts' });

/**
 * One reference of a node to another, named by the field that holds it.
 */
export class NodeReference {
  /**
   * @param {string} field The field holding the reference.
   * @param {string} target The identity of the node referred to.
   */
  constructor(field, target) {
    /**
     * The field holding the reference.
     * @type {string}
     */
    this.field = field;
    /**
     * The identity of the node referred to.
     * @type {string}
     */
    this.target = target;
  }
}

export class GraphNode {
  /**
   * @param {Object} parts The node's parts: `identifier`, `kind` (a `NodeKind` value),
   *   `label`, `parent` (the identity of its parent in the tree, or null), `fields`
   *   (`[name, value]` pairs), `references` (`NodeReference`s) and `keys` (the viewer
   *   keys the node lights up).
   */
  constructor(parts) {
    /**
     * The node's identity.
     * @type {string}
     */
    this.identifier = parts.identifier;
    /**
     * What it stands for, a `NodeKind` value.
     * @type {string}
     */
    this.kind = parts.kind;
    /**
     * Its name for people.
     * @type {string}
     */
    this.label = parts.label;
    /**
     * Its parent in the tree, or null for the world.
     * @type {string|null}
     */
    this.parent = parts.parent ?? null;
    /**
     * What is known about it, as `[name, value]` pairs.
     * @type {Array<[string, string]>}
     */
    this.fields = parts.fields ?? [];
    /**
     * The nodes it depends on.
     * @type {Array<NodeReference>}
     */
    this.references = parts.references ?? [];
    /**
     * The viewer keys it lights up in the 3D view.
     * @type {Array<string>}
     */
    this.keys = parts.keys ?? [];
  }
}

// %% facts

/**
 * @param {Array<number>|undefined} axis A joint axis.
 * @returns {string} The axis, rounded.
 */
function axisText(axis) {
  return axis ? `(${axis.map((value) => Math.round(value * 1000) / 1000).join(', ')})` : '';
}

/**
 * @param {number|undefined} lower A joint's lower limit.
 * @param {number|undefined} upper Its upper limit.
 * @returns {string} The range, or '' without limits.
 */
function rangeText(lower, upper) {
  return Number.isFinite(lower) && Number.isFinite(upper) && (lower !== 0 || upper !== 0) ? `${lower} … ${upper}` : '';
}

/**
 * @param {Array<[string, string]>} fields Fields, some without a value.
 * @returns {Array<[string, string]>} The fields that have one.
 */
function given(fields) {
  return fields.filter(([, value]) => value !== undefined && value !== null && value !== '');
}

// %% graph

export class SceneGraph {
  /**
   * The nodes by identity, in the order they were added.
   * @type {Map<string, GraphNode>}
   */
  #nodes = new Map();

  /**
   * @param {Array<GraphNode>} nodes The graph's nodes, parents before their children.
   */
  constructor(nodes) {
    for (const node of nodes) this.#nodes.set(node.identifier, node);
  }

  /**
   * @param {Object} facts What the scene holds: `name`; `models`, each `{name, robot,
   *   urdf, links}` with links `{name, parent, joint}` and a joint `{name, type, axis,
   *   lower, upper}` or null for the root; `objects`, each `{key, name}`; and `parts`,
   *   each `{name, role, side, links, attachedTo}`.
   * @returns {SceneGraph} The graph of the scene.
   */
  static of(facts) {
    const nodes = [new GraphNode({ identifier: FixedNode.WORLD, kind: NodeKind.WORLD, label: facts.name || 'World', fields: [['Scene', facts.name]] })];
    const linkNodes = new Map();
    for (const model of facts.models) {
      const identifier = `model:${model.name}`;
      const root = model.links.find((link) => !link.parent);
      nodes.push(
        new GraphNode({
          identifier,
          kind: NodeKind.MODEL,
          label: model.name,
          parent: FixedNode.WORLD,
          fields: given([['Kind', model.robot ? 'robot' : 'environment'], ['Description', model.urdf], ['Links', String(model.links.length)]]),
          references: root ? [new NodeReference('root link', `link:${model.name}/${root.name}`)] : [],
          keys: root ? [root.name] : [],
        }),
      );
      for (const link of SceneGraph.#parentsFirst(model.links)) {
        const linkIdentifier = `link:${model.name}/${link.name}`;
        const joint = link.joint;
        nodes.push(
          new GraphNode({
            identifier: linkIdentifier,
            kind: NodeKind.LINK,
            label: link.name,
            parent: link.parent ? `link:${model.name}/${link.parent}` : identifier,
            fields: given([
              ['Model', model.name],
              ['Joint', joint?.name],
              ['Joint type', joint?.type],
              ['Axis', joint && joint.type !== 'fixed' ? axisText(joint.axis) : ''],
              ['Range', joint ? rangeText(joint.lower, joint.upper) : ''],
            ]),
            references: link.parent ? [new NodeReference('parent link', `link:${model.name}/${link.parent}`)] : [],
            keys: [link.name],
          }),
        );
        if (!linkNodes.has(link.name) || model.robot) linkNodes.set(link.name, linkIdentifier);
      }
    }
    if (facts.objects.length) nodes.push(new GraphNode({ identifier: FixedNode.OBJECTS, kind: NodeKind.GROUP, label: 'Free objects', parent: FixedNode.WORLD }));
    for (const object of facts.objects) {
      nodes.push(
        new GraphNode({
          identifier: `object:${object.key}`,
          kind: NodeKind.OBJECT,
          label: object.name,
          parent: FixedNode.OBJECTS,
          fields: given([['Key', object.key]]),
          keys: [object.key],
        }),
      );
    }
    if (facts.parts.length) nodes.push(new GraphNode({ identifier: FixedNode.PARTS, kind: NodeKind.GROUP, label: 'Robot parts', parent: FixedNode.WORLD }));
    const partNames = new Set(facts.parts.map((part) => part.name));
    for (const part of facts.parts) {
      const references = part.links.filter((link) => linkNodes.has(link)).map((link) => new NodeReference('link', linkNodes.get(link)));
      if (part.attachedTo && partNames.has(part.attachedTo)) references.push(new NodeReference('attached to', `part:${part.attachedTo}`));
      nodes.push(
        new GraphNode({
          identifier: `part:${part.name}`,
          kind: NodeKind.PART,
          label: part.name,
          parent: FixedNode.PARTS,
          fields: given([['Role', part.role?.replace('_', ' ')], ['Side', part.side], ['Links', String(part.links.length)]]),
          references,
          keys: part.links,
        }),
      );
    }
    return new SceneGraph(nodes);
  }

  /**
   * @param {Array<Object>} links A model's links.
   * @returns {Array<Object>} The links, each after its parent.
   */
  static #parentsFirst(links) {
    const byName = new Map(links.map((link) => [link.name, link]));
    const ordered = [];
    const placed = new Set();
    const place = (link) => {
      if (placed.has(link.name)) return;
      placed.add(link.name);
      if (link.parent && byName.has(link.parent)) place(byName.get(link.parent));
      ordered.push(link);
    };
    links.forEach(place);
    return ordered;
  }

  /**
   * @param {string} identifier A node's identity.
   * @returns {GraphNode|undefined} The node.
   */
  node(identifier) {
    return this.#nodes.get(identifier);
  }

  /**
   * @param {string|null} identifier A node's identity, or null for the tree's top.
   * @returns {Array<GraphNode>} Its children, in the order they were added.
   */
  children(identifier) {
    return [...this.#nodes.values()].filter((node) => node.parent === identifier);
  }

  /**
   * @param {string} identifier A node's identity.
   * @returns {Array<{field: string, source: GraphNode}>} The nodes referring to it.
   */
  referencedBy(identifier) {
    return [...this.#nodes.values()].flatMap((node) => node.references.filter((reference) => reference.target === identifier).map((reference) => ({ field: reference.field, source: node })));
  }

  /**
   * @param {string} identifier A node's identity.
   * @returns {Array<string>} The identities from the world down to the node's parent.
   */
  ancestors(identifier) {
    const path = [];
    let current = this.#nodes.get(identifier)?.parent ?? null;
    while (current) {
      path.unshift(current);
      current = this.#nodes.get(current)?.parent ?? null;
    }
    return path;
  }

  /**
   * @returns {Map<string, number>} How many nodes of each kind the graph holds, without
   *   the world and the groups.
   */
  counts() {
    const counts = new Map();
    for (const node of this.#nodes.values()) {
      if (node.kind === NodeKind.WORLD || node.kind === NodeKind.GROUP) continue;
      counts.set(node.kind, (counts.get(node.kind) ?? 0) + 1);
    }
    return counts;
  }

  /**
   * @param {string} text What a filter asks for.
   * @returns {Set<string>|null} The nodes whose label holds the text, whatever its case,
   *   with their ancestors, or null when the text asks for nothing.
   */
  matching(text) {
    const wanted = text.trim().toLowerCase();
    if (!wanted) return null;
    const shown = new Set();
    for (const node of this.#nodes.values()) {
      if (!node.label.toLowerCase().includes(wanted)) continue;
      shown.add(node.identifier);
      for (const ancestor of this.ancestors(node.identifier)) shown.add(ancestor);
    }
    return shown;
  }

  /**
   * @param {string} kind What the 3D view selected, a `SelectionKind` value: a link of a
   *   model or an object.
   * @param {string} name The link's name or the object's key.
   * @param {string=} model The model of a link.
   * @returns {string|null} The node standing for it, or null.
   */
  nodeOf(kind, name, model) {
    const identifier = kind === NodeKind.OBJECT ? `object:${name}` : `link:${model}/${name}`;
    return this.#nodes.has(identifier) ? identifier : null;
  }
}
