/**
 * The chain the Designators layout shows for one moment of a recorded or live run: the
 * top-level action designator under way, the role each of its fields fills and the
 * entities of the semantic digital twin each names, and the entity queries whose
 * answers named those entities, with the frame each was asked at.
 *
 * The roles are cramera's reading of the designators' fields, written by the bridge; a
 * query is linked to a role by the entities its answers light up, not by anything the
 * plan records about where its fields came from. A role whose entities no query named
 * was filled by the plan's own code: a value the program wrote, or a pose it computed.
 */

import {
  PlanNodeKey,
  PlanNodeKind,
  QueryStepKey,
  QueryStepsKey,
  RoleEntityKey,
  RoleSlotKey,
  RoleSource,
  StepPhase,
} from '../protocol.js';

// %% phases

/**
 * Where a plan node stands at a moment of the run.
 */
export const NodePhase = Object.freeze({
  PENDING: 'pending',
  RUNNING: 'running',
  SUCCEEDED: 'succeeded',
  FAILED: 'failed',
  INTERRUPTED: 'interrupted',
  NOT_RUN: 'not run',
  ENDED: 'ended',
});

/**
 * The phase a node that ended is in, by the status the recording ended with.
 */
const ENDED_PHASES = Object.freeze({
  SUCCEEDED: NodePhase.SUCCEEDED,
  FAILED: NodePhase.FAILED,
  INTERRUPTED: NodePhase.INTERRUPTED,
  CREATED: NodePhase.NOT_RUN,
  RUNNING: NodePhase.INTERRUPTED,
  PAUSE: NodePhase.INTERRUPTED,
});

/**
 * Where a query's answers come from, as the layout marks them.
 */
export const AnswerOrigin = Object.freeze({
  LIVE: 'LIVE',
  RECORDED: 'RECORDED',
});

/**
 * How a role was filled.
 */
export const Filling = Object.freeze({
  QUERIED: 'queried',
  FROM_CONTEXT: 'from the plan context',
  WRITTEN: 'written by the plan code',
  COMPUTED: 'pose computed by the plan code',
});

/**
 * One plan node with its phase at a moment.
 */
export class NodeAtFrame {
  /**
   * @param {Object} node The plan node, as the scene's plan trees hold it.
   * @param {string} phase Its phase, one of {@link NodePhase}.
   * @param {boolean} inferred Whether the phase is read from the node's ancestors, as
   *   for a node the recording gives no frames of its own.
   * @param {Array<NodeAtFrame>} children Its children.
   */
  constructor(node, phase, inferred, children) {
    this.node = node;
    this.phase = phase;
    this.inferred = inferred;
    this.children = children;
  }

  /**
   * @returns {string|null} The node's identity.
   */
  get identifier() {
    return this.node[PlanNodeKey.IDENTIFIER] ?? null;
  }
}

/**
 * @param {Object} node A plan node.
 * @param {number} frame The frame shown.
 * @param {string|null} inherited The phase of the nearest ancestor with frames, or
 *   null for none.
 * @returns {{phase: string, inferred: boolean}} The node's phase: from its own frames
 *   where it has them, a node that ran but whose own status coraplex never set, such as
 *   a sequence, ending as ended; otherwise pending or running with its ancestor, as a
 *   condition or an attachment, which take no time of their own, and once the ancestor
 *   ended, the status the recording ended with.
 */
export function phaseOf(node, frame, inherited) {
  const start = node[PlanNodeKey.START];
  const end = node[PlanNodeKey.END];
  const ended = ENDED_PHASES[node[PlanNodeKey.STATUS]] ?? NodePhase.NOT_RUN;
  if (start === null || start === undefined) {
    if (inherited === NodePhase.PENDING || inherited === NodePhase.RUNNING) return { phase: inherited, inferred: true };
    return { phase: ended, inferred: true };
  }
  if (frame < start) return { phase: NodePhase.PENDING, inferred: false };
  if (frame <= end) return { phase: NodePhase.RUNNING, inferred: false };
  return { phase: ended === NodePhase.NOT_RUN ? NodePhase.ENDED : ended, inferred: false };
}

/**
 * @param {Object} node A plan node.
 * @param {number} frame The frame shown.
 * @param {string|null} inherited The phase of the node's parent.
 * @returns {NodeAtFrame} The node and its descendants with their phases.
 */
export function nodeAtFrame(node, frame, inherited = null) {
  const { phase, inferred } = phaseOf(node, frame, inherited);
  const children = (node[PlanNodeKey.CHILDREN] ?? []).map((child) => nodeAtFrame(child, frame, phase));
  return new NodeAtFrame(node, phase, inferred, children);
}

// %% actions

/**
 * @param {Array<Object>} roots The scene's plan trees.
 * @returns {Array<Object>} The top-level actions, in plan order: the actions no other
 *   action encloses.
 */
export function topLevelActions(roots) {
  const found = [];
  const visit = (node) => {
    if (node[PlanNodeKey.KIND] === PlanNodeKind.ACTION) {
      found.push(node);
      return;
    }
    (node[PlanNodeKey.CHILDREN] ?? []).forEach(visit);
  };
  roots.forEach(visit);
  return found;
}

/**
 * @param {Array<Object>} roots The scene's plan trees.
 * @param {number} frame The frame shown.
 * @returns {Object|null} The top-level action the frame falls in; between actions the
 *   one that ran last, before the first the first; null for a plan without actions.
 */
export function actionAt(roots, frame) {
  const actions = topLevelActions(roots).filter((action) => action[PlanNodeKey.START] !== null && action[PlanNodeKey.START] !== undefined);
  if (!actions.length) return topLevelActions(roots)[0] ?? null;
  const started = actions.filter((action) => action[PlanNodeKey.START] <= frame);
  return started.length ? started[started.length - 1] : actions[0];
}

/**
 * @param {NodeAtFrame} tree An action with its phases.
 * @returns {NodeAtFrame|null} Its deepest running descendant with frames of its own,
 *   the action itself, or null when nothing runs.
 */
export function runningNode(tree) {
  if (tree.phase !== NodePhase.RUNNING) return null;
  for (const child of tree.children) {
    const running = runningNode(child);
    if (running && !running.inferred) return running;
  }
  return tree;
}

/**
 * @param {Object} node A plan node.
 * @returns {Array<Object>} The node and its descendants, in plan order.
 */
export function subtree(node) {
  return [node, ...(node[PlanNodeKey.CHILDREN] ?? []).flatMap(subtree)];
}

// %% roles

/**
 * One entity of the semantic digital twin with a role in the action.
 */
export class RoleRow {
  /**
   * @param {Object} fields The row's fields.
   * @param {string} fields.name The entity's name.
   * @param {string} fields.type The entity's class.
   * @param {string} fields.role The role it fills.
   * @param {string} fields.field The field that names it.
   * @param {string} fields.designator The designator whose field it is.
   * @param {string|null} fields.node The identity of that designator's plan node.
   * @param {Array<string>} fields.keys What the scene lights up for it.
   * @param {boolean} fields.reference Whether it is only the frame a pose is given in.
   * @param {string|null} fields.place The name the task gave the place the pose
   *   stands for, such as `centrifuge C4`, or null.
   */
  constructor({ name, type, role, field, designator, node, keys, reference, place = null }) {
    this.name = name;
    this.type = type;
    this.role = role;
    this.field = field;
    this.designator = designator;
    this.node = node;
    this.keys = keys;
    this.reference = reference;
    this.place = place;
  }
}

/**
 * @param {Object} node A plan node.
 * @returns {Array<Object>} Its role slots; none in recordings written before roles.
 */
export function rolesOf(node) {
  return node[PlanNodeKey.ROLES] ?? [];
}

/**
 * @param {Object} action A top-level action.
 * @returns {Array<RoleRow>} Every entity a role of the action or of a designator
 *   inside it names, once per entity, role and field, in plan order; a pose's
 *   reference body counts as an entity of the pose's role.
 */
export function roleRows(action) {
  const rows = new Map();
  for (const node of subtree(action)) {
    for (const slot of rolesOf(node)) {
      const named = (slot[RoleSlotKey.ENTITIES] ?? []).map((entity) => [entity, false]);
      if (slot[RoleSlotKey.REFERENCE]) named.push([slot[RoleSlotKey.REFERENCE], true]);
      for (const [entity, reference] of named) {
        const row = new RoleRow({
          name: entity[RoleEntityKey.NAME],
          type: entity[RoleEntityKey.TYPE],
          role: slot[RoleSlotKey.ROLE],
          field: slot[RoleSlotKey.FIELD],
          designator: node[PlanNodeKey.LABEL],
          node: node[PlanNodeKey.IDENTIFIER] ?? null,
          keys: entity[RoleEntityKey.KEYS] ?? [],
          reference,
          place: reference ? slot[RoleSlotKey.PLACE] ?? null : null,
        });
        const identity = `${row.name}|${row.role}|${row.field}|${row.place}`;
        if (!rows.has(identity)) rows.set(identity, row);
      }
    }
  }
  return [...rows.values()];
}

/**
 * @param {Array<RoleRow>} rows The rows shown.
 * @param {string} key A key the 3D view selected: a link's name or a free object's key.
 * @returns {Array<RoleRow>} The rows whose entity the key belongs to.
 */
export function rowsOfKey(rows, key) {
  return rows.filter((row) => row.keys.includes(key));
}

// %% queries

/**
 * @param {Object|null} querySteps The run's query steps document, or null.
 * @returns {Array<Object>} Its steps, in the order they were asked.
 */
export function stepsOf(querySteps) {
  return [...(querySteps?.[QueryStepsKey.STEPS] ?? [])].sort((a, b) => a[QueryStepKey.NUMBER] - b[QueryStepKey.NUMBER]);
}

/**
 * @param {Object} entity An entity of the world, as a role or an answer names it.
 * @returns {string} Its identity in the scene: the keys it lights up, in order; an
 *   annotation and the one body it stands for, such as a container and its vessel,
 *   share it.
 */
export function entityIdentity(entity) {
  return [...new Set(entity[RoleEntityKey.KEYS] ?? [])].sort().join('|');
}

/**
 * @param {Object} slot A role slot.
 * @returns {Array<Object>} The entities it names, its pose's reference included.
 */
export function slotEntities(slot) {
  const entities = [...(slot[RoleSlotKey.ENTITIES] ?? [])];
  if (slot[RoleSlotKey.REFERENCE]) entities.push(slot[RoleSlotKey.REFERENCE]);
  return entities;
}

/**
 * @param {Object} step A query step.
 * @returns {Array<Object>} The entities of the world among its answers.
 */
export function answerEntities(step) {
  return step[QueryStepKey.ENTITIES] ?? [];
}

/**
 * How one role of a designator was filled.
 */
export class SlotResolution {
  /**
   * @param {Object} fields The resolution's fields.
   * @param {Object} fields.node The designator's plan node.
   * @param {Object} fields.slot The role slot.
   * @param {string} fields.filling How it was filled, one of {@link Filling}.
   * @param {Array<Object>} fields.steps The queries whose answers named its entities,
   *   in the order they were asked.
   */
  constructor({ node, slot, filling, steps }) {
    this.node = node;
    this.slot = slot;
    this.filling = filling;
    this.steps = steps;
  }
}

/**
 * @param {Object} slot A role slot.
 * @param {Array<Object>} steps The run's query steps.
 * @param {number|null} before Only queries asked at or before this frame, or null for
 *   every query.
 * @returns {Array<Object>} The queries one of whose answers is an entity the slot
 *   names, the same keys lit up; a query answering with every entity of a kind, such
 *   as every handle, counts when one of its answers is the slot's. A part of an answer,
 *   such as the arm of the robot a query answered, does not.
 */
export function stepsNaming(slot, steps, before = null) {
  const identities = new Set(slotEntities(slot).map(entityIdentity).filter(Boolean));
  if (!identities.size) return [];
  return steps.filter((step) => {
    const frame = step[QueryStepKey.FRAME];
    if (before !== null && frame !== null && frame !== undefined && frame > before) return false;
    return answerEntities(step).some((entity) => identities.has(entityIdentity(entity)));
  });
}

/**
 * @param {Object} slot A role slot no query named.
 * @returns {string} How it was filled instead, one of {@link Filling}.
 */
export function fillingWithoutQuery(slot) {
  if (slot[RoleSlotKey.SOURCE] === RoleSource.CONTEXT) return Filling.FROM_CONTEXT;
  if (slot[RoleSlotKey.REFERENCE] && !(slot[RoleSlotKey.ENTITIES] ?? []).length) return Filling.COMPUTED;
  return Filling.WRITTEN;
}

/**
 * @param {Object} node A designator's plan node.
 * @param {Array<Object>} steps The run's query steps.
 * @returns {Array<SlotResolution>} How each of its roles was filled: by the queries
 *   asked before the node started whose answers name the role's entities, else by
 *   the context or the plan's code.
 */
export function slotResolutions(node, steps) {
  const start = node[PlanNodeKey.START] ?? null;
  return rolesOf(node).map((slot) => {
    const naming = stepsNaming(slot, steps, start);
    return new SlotResolution({
      node,
      slot,
      filling: naming.length ? Filling.QUERIED : fillingWithoutQuery(slot),
      steps: naming,
    });
  });
}

/**
 * @param {Object} action A top-level action.
 * @param {Array<Object>} steps The run's query steps.
 * @returns {Array<Object>} The queries the action relates to, in the order asked:
 *   those asked while it or a node inside it ran, and those whose answers name an
 *   entity one of its roles names.
 */
export function stepsOfAction(action, steps) {
  const nodes = subtree(action);
  const identities = new Set(nodes.map((node) => node[PlanNodeKey.IDENTIFIER]).filter(Boolean));
  const named = new Set(nodes.flatMap((node) => slotResolutions(node, steps)).flatMap((resolution) => resolution.steps));
  return steps.filter((step) => named.has(step) || identities.has(step[QueryStepKey.PLAN_NODE]));
}

/**
 * @param {Object} step A query step.
 * @param {Object} action The action it relates to.
 * @returns {string} When it was asked relative to the action: while the plans were
 *   built, before the action ran, or while it ran.
 */
export function whenAsked(step, action) {
  const phase = step[QueryStepKey.PHASE];
  if (step[QueryStepKey.PLAN_NODE] && subtree(action).some((node) => node[PlanNodeKey.IDENTIFIER] === step[QueryStepKey.PLAN_NODE])) return 'while the action ran';
  if (phase === StepPhase.SETUP || phase === StepPhase.EXPANSION) return 'while the plans were built, before any motion';
  if (phase === StepPhase.RESOLUTION) return 'while an open part of the plan was resolved';
  return 'before the action ran';
}
