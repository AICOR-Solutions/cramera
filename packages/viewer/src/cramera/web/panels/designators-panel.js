/**
 * The Designators panel, three panes bound to the top-level action under way at the
 * frame shown: the entities of the semantic digital twin that fill a role in it, the
 * action designator as a tree with its role slots and each node's phase, and how each
 * role was filled, with the entity queries, in the order asked, whose answers named
 * its entities. With `?layout=designators` the page shows the 3D view and this panel
 * side by side and nothing else.
 *
 * Every answer is marked RECORDED when it is replayed from the bundle's query steps and
 * LIVE only when a running process published it; the queries are entity queries over
 * the twin's working memory, which is what the run asked, not KnowRob.
 */

import {
  BackendDescriptionKey,
  PlanNodeKey,
  QueryStepKey,
  RoleSlotKey,
  RoleSource,
  SceneKey,
  SelectionKey,
  VerbalizationKey,
  ViewerEvent,
} from '../protocol.js';
import {
  actionAt,
  AnswerOrigin,
  Filling,
  NodePhase,
  nodeAtFrame,
  roleRows,
  rolesOf,
  rowsOfKey,
  runningNode,
  slotResolutions,
  stepsOf,
  stepsOfAction,
  subtree,
  whenAsked,
} from '../designators/designator-chain.js';
import { element } from './elements.js';
import { SidePanel } from './panel-host.js';

/**
 * The panel's identity, which `?panel=` names.
 */
export const DESIGNATORS_PANEL = 'designators';

/**
 * What the panel says for a scene without plan trees.
 */
export const NO_PLAN = 'This scene recorded no plan, so no designator is shown.';

/**
 * What the panel says for a recording written before designators named their roles.
 */
export const NO_ROLES = 'This recording was written before the bridge recorded the roles of designators; record it again to see them.';

/**
 * What the panel says for a recording without query steps.
 */
export const NO_STEPS = 'The run recorded no query steps: run it with --step-queries to see how its designators were resolved.';

/**
 * What the resolution pane says of the backend: what the queries actually ask.
 */
export const BACKEND_NOTE = 'Entity queries (krrood EQL) over the semantic digital twin’s working memory, as the run asked them; no KnowRob query was issued.';

/**
 * What the panel says of the roles: whose reading they are.
 */
export const ROLES_NOTE = 'Roles are cramera’s reading of the designator’s CRAM fields (shown beside each role); CRAM itself names fields, not roles. Place names such as centrifuge C4 are the task’s, from its bench layout.';

export class DesignatorsPanel {
  /**
   * The panel.
   * @type {SidePanel}
   */
  panel;

  /**
   * The bus the panel lights entities up and requests frames on.
   * @type {import('../core/event-bus.js').EventBus}
   */
  #bus;

  /**
   * The shown scene's plan trees.
   * @type {Array<Object>}
   */
  roots = [];

  /**
   * The shown run's query steps, in the order asked.
   * @type {Array<Object>}
   */
  steps = [];

  /**
   * Where the steps' answers come from.
   * @type {string}
   */
  origin = AnswerOrigin.RECORDED;

  /**
   * The frame shown.
   * @type {number}
   */
  frame = 0;

  /**
   * The top-level action shown, or null.
   * @type {Object|null}
   */
  action = null;

  /**
   * The rows of the roles pane.
   * @type {Array<import('../designators/designator-chain.js').RoleRow>}
   */
  rows = [];

  /**
   * The keys of the entity selected in either view, or null.
   * @type {Array<string>|null}
   */
  selected = null;

  /**
   * The panes' bodies.
   * @type {{roles: HTMLElement, tree: HTMLElement, resolution: HTMLElement, title: HTMLElement}}
   */
  #panes;

  /**
   * @param {Document} document The page.
   * @param {import('../core/event-bus.js').EventBus} bus The bus the panel lights
   *   entities up and requests frames on.
   */
  constructor(document, bus) {
    this.#bus = bus;
    this.panel = new SidePanel(DESIGNATORS_PANEL, 'Designators', element(document, 'section', 'designators'));
    const pane = (title, note) => {
      const body = element(document, 'div', 'designators-body');
      const section = element(document, 'section', 'designators-pane', null, [element(document, 'h3', '', title)]);
      if (note) section.append(element(document, 'p', 'muted designators-note', note));
      section.append(body);
      return { section, body };
    };
    const title = element(document, 'p', 'designators-action');
    const roles = pane('SDT entities with roles in the action', ROLES_NOTE);
    const tree = pane('Action designator', null);
    const resolution = pane('Interpretation and resolution', BACKEND_NOTE);
    this.panel.element.append(title, roles.section, tree.section, resolution.section);
    this.#panes = { title, roles: roles.body, tree: tree.body, resolution: resolution.body };
    bus.subscribe(ViewerEvent.FRAME_CHANGED, (frame) => this.showFrame(frame ?? 0));
    bus.subscribe(ViewerEvent.ENTITY_SELECTED, (selection) => this.selectKey(selection?.[SelectionKey.NAME] ?? null));
    this.render();
  }

  /**
   * Show a recorded scene: its plan trees and the query steps it recorded.
   * @param {import('../scene/scene-loader.js').LoadedScene} scene The shown scene.
   */
  show(scene) {
    this.roots = scene.description[SceneKey.PLAN_TREES] ?? [];
    this.showSteps(scene.querySteps, AnswerOrigin.RECORDED);
  }

  /**
   * @param {Object|null} querySteps A query steps document.
   * @param {string} origin Where its answers come from, one of {@link AnswerOrigin}.
   */
  showSteps(querySteps, origin) {
    this.steps = stepsOf(querySteps);
    this.origin = origin;
    this.render();
  }

  /**
   * @param {number} frame The frame the playback shows.
   */
  showFrame(frame) {
    this.frame = frame;
    this.render();
  }

  /**
   * Mark the rows of the entity a key belongs to, as when the 3D view selected it.
   * @param {string|null} key A link's name or a free object's key, or null.
   */
  selectKey(key) {
    const rows = key === null ? [] : rowsOfKey(this.rows, key);
    this.selected = rows.length ? rows[0].keys : null;
    this.render();
  }

  /**
   * Light up a row's entity in the 3D view and mark it.
   * @param {import('../designators/designator-chain.js').RoleRow} row The row.
   */
  selectRow(row) {
    this.selected = row.keys;
    this.#bus.publish(ViewerEvent.ENTITY_HIGHLIGHTED, row.keys);
    if (row.keys.length) this.#bus.publish(ViewerEvent.FOCUS_REQUESTED, row.keys);
    this.render();
  }

  /**
   * Draw the three panes for the frame shown.
   */
  render() {
    const document = this.panel.element.ownerDocument;
    const panes = this.#panes;
    this.action = actionAt(this.roots, this.frame);
    if (!this.action) {
      this.rows = [];
      panes.title.textContent = NO_PLAN;
      for (const body of [panes.roles, panes.tree, panes.resolution]) body.replaceChildren();
      return;
    }
    const tree = nodeAtFrame(this.action, this.frame);
    const running = runningNode(tree);
    panes.title.replaceChildren(
      element(document, 'span', 'muted', 'Top-level action at frame '),
      element(document, 'strong', '', this.frame),
      element(document, 'span', 'muted', ': '),
      element(document, 'strong', '', this.action[PlanNodeKey.LABEL]),
      element(document, 'span', `designator-phase phase-${tree.phase.replace(' ', '-')}`, tree.phase),
    );
    this.rows = roleRows(this.action);
    const hasRoles = subtree(this.action).some((node) => rolesOf(node).length);
    panes.roles.replaceChildren(hasRoles ? this.#rolesTable(document) : element(document, 'p', 'muted', NO_ROLES));
    panes.tree.replaceChildren(element(document, 'ol', 'designator-tree', null, [this.#treeNode(document, tree, running)]));
    panes.resolution.replaceChildren(...this.#resolution(document, running?.node ?? this.action));
  }

  /**
   * @param {Document} document The page.
   * @returns {HTMLElement} The roles pane's table.
   */
  #rolesTable(document) {
    const head = element(document, 'tr', '', null, ['Entity', 'Type', 'Role', 'Field', 'Designator'].map((text) => element(document, 'th', '', text)));
    const rows = this.rows.map((row) => {
      const selected = this.selected !== null && this.selected.join('|') === row.keys.join('|');
      const tr = element(document, 'tr', selected ? 'role-row selected' : 'role-row', null, [
        element(document, 'td', 'role-entity', row.name, row.place ? [element(document, 'span', 'role-place', row.place)] : []),
        element(document, 'td', 'muted', row.type),
        element(document, 'td', `role-name role-${row.role}`, row.reference ? `${row.role} (frame)` : row.role),
        element(document, 'td', 'mono', row.field),
        element(document, 'td', 'muted', row.designator),
      ]);
      tr.dataset.keys = row.keys.join(' ');
      tr.tabIndex = 0;
      tr.title = 'Light it up in the 3D view';
      tr.addEventListener('click', () => this.selectRow(row));
      tr.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') this.selectRow(row);
      });
      return tr;
    });
    return element(document, 'table', 'role-table', null, [element(document, 'thead', '', null, [head]), element(document, 'tbody', '', null, rows)]);
  }

  /**
   * @param {Document} document The page.
   * @param {import('../designators/designator-chain.js').NodeAtFrame} at A node with its phase.
   * @param {import('../designators/designator-chain.js').NodeAtFrame|null} running The node running deepest.
   * @returns {HTMLElement} The node's line, its role slots and its children.
   */
  #treeNode(document, at, running) {
    const node = at.node;
    const phase = element(document, 'span', `designator-phase phase-${at.phase.replace(' ', '-')}${at.inferred ? ' inferred' : ''}`, at.phase);
    if (at.inferred) phase.title = 'No frames of its own were recorded; read from the enclosing node';
    else if (at.phase === NodePhase.ENDED) phase.title = 'Ran in these frames; coraplex recorded no outcome of its own for it';
    const line = element(document, 'div', running === at ? 'designator-line current' : 'designator-line', null, [
      element(document, 'span', 'designator-kind', node[PlanNodeKey.KIND]),
      element(document, 'strong', '', node[PlanNodeKey.LABEL]),
      phase,
    ]);
    if (node[PlanNodeKey.START] !== null && node[PlanNodeKey.START] !== undefined) {
      line.append(element(document, 'span', 'muted', `frames ${node[PlanNodeKey.START]}–${node[PlanNodeKey.END]}`));
      line.title = 'Show the moment it started';
      line.addEventListener('click', () => this.#bus.publish(ViewerEvent.FRAME_REQUESTED, node[PlanNodeKey.START]));
    }
    const item = element(document, 'li', 'designator-node', null, [line]);
    item.dataset.phase = at.phase;
    const slots = rolesOf(node);
    if (slots.length) {
      item.append(element(document, 'ul', 'role-slots', null, slots.map((slot) => element(document, 'li', '', null, [
        element(document, 'span', `role-name role-${slot[RoleSlotKey.ROLE]}`, slot[RoleSlotKey.ROLE]),
        element(document, 'span', 'mono', ` ${slot[RoleSlotKey.FIELD]}`),
        element(document, 'span', '', ` = ${slot[RoleSlotKey.VALUE]}`),
        slot[RoleSlotKey.PLACE] ? element(document, 'span', 'role-place', slot[RoleSlotKey.PLACE]) : '',
        slot[RoleSlotKey.SOURCE] === RoleSource.CONTEXT ? element(document, 'span', 'muted', ' (plan context)') : '',
      ]))));
    }
    const shown = at.children.filter((child) => child.node[PlanNodeKey.KIND] !== 'condition');
    if (shown.length) item.append(element(document, 'ol', 'designator-children', null, shown.map((child) => this.#treeNode(document, child, running))));
    return item;
  }

  /**
   * @param {Document} document The page.
   * @param {Object} node The designator running deepest, or the action.
   * @returns {Array<HTMLElement>} How the designator and the action were resolved.
   */
  #resolution(document, node) {
    const parts = [];
    const designators = [...new Set([node, this.action])].filter((each) => rolesOf(each).length);
    for (const designator of designators) {
      parts.push(element(document, 'h4', '', `${designator[PlanNodeKey.LABEL]}: how its roles were filled`));
      const list = element(document, 'ul', 'slot-resolutions');
      for (const resolution of slotResolutions(designator, this.steps)) {
        const slot = resolution.slot;
        const entry = element(document, 'li', `slot-resolution filling-${resolution.filling === Filling.QUERIED ? 'queried' : 'unqueried'}`, null, [
          element(document, 'span', `role-name role-${slot[RoleSlotKey.ROLE]}`, slot[RoleSlotKey.ROLE]),
          element(document, 'span', 'mono', ` ${slot[RoleSlotKey.FIELD]} `),
          element(document, 'span', '', `→ ${slot[RoleSlotKey.VALUE]}`),
          slot[RoleSlotKey.PLACE] ? element(document, 'span', 'role-place', slot[RoleSlotKey.PLACE]) : '',
          element(document, 'span', 'slot-filling', resolution.filling),
        ]);
        if (resolution.steps.length) entry.append(element(document, 'span', 'muted', ` by query ${resolution.steps.map((step) => `#${step[QueryStepKey.NUMBER]}`).join(', ')}`));
        list.append(entry);
      }
      parts.push(list);
    }
    parts.push(element(document, 'h4', '', 'Queries, in the order asked'));
    if (!this.steps.length) {
      parts.push(element(document, 'p', 'muted', NO_STEPS));
      return parts;
    }
    const related = stepsOfAction(this.action, this.steps);
    if (!related.length) {
      parts.push(element(document, 'p', 'muted', 'No query the run asked named an entity of this action’s roles.'));
      return parts;
    }
    parts.push(element(document, 'ol', 'designator-queries', null, related.map((step) => this.#step(document, step))));
    return parts;
  }

  /**
   * @param {Document} document The page.
   * @param {Object} step A query step.
   * @returns {HTMLElement} The query with its answers and where they come from.
   */
  #step(document, step) {
    const question = step[QueryStepKey.QUESTION]?.[VerbalizationKey.TEXT] ?? '(not worded)';
    const backend = step[QueryStepKey.BACKEND] ?? {};
    const frame = step[QueryStepKey.FRAME];
    const origin = element(document, 'span', `answer-origin origin-${this.origin.toLowerCase()}`, this.origin);
    origin.title = this.origin === AnswerOrigin.LIVE ? 'Published by the running process' : 'Replayed from the recorded query steps; nothing was queried now';
    const item = element(document, 'li', 'designator-query', null, [
      element(document, 'div', 'query-head', null, [
        element(document, 'strong', '', `#${step[QueryStepKey.NUMBER]} `),
        element(document, 'span', '', question),
        origin,
      ]),
      element(document, 'p', 'muted', `${backend[BackendDescriptionKey.NAME] ?? 'backend'} · ${backend[BackendDescriptionKey.SOURCE] ?? ''} · ${frame === null || frame === undefined ? 'frame not recorded' : `frame ${frame}`} · ${whenAsked(step, this.action)}`),
    ]);
    const answers = step[QueryStepKey.ANSWERS] ?? [];
    item.append(element(document, 'ul', 'query-answers', null, answers.map((answer) => element(document, 'li', '', null, [
      element(document, 'span', 'mono', answer),
      element(document, 'span', `answer-origin origin-${this.origin.toLowerCase()}`, this.origin),
    ]))));
    return item;
  }
}

export { NodePhase };
