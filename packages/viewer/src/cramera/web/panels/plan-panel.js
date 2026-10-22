/**
 * The executed plans of a recording, as a tree of plan nodes with the life-cycle state
 * each had when the run ended.
 */

import { LivePlanKey, LivePlanNodeKey, PlanNodeKey } from '../protocol.js';
import { SidePanel } from './panel-host.js';

// %% panel

export class PlanPanel {
  /**
   * The panel.
   * @type {SidePanel}
   */
  panel;

  /**
   * @param {Document} document The page.
   */
  constructor(document) {
    this.panel = new SidePanel('plan', 'Plan', document.createElement('section'));
  }

  /**
   * @param {Array<Object>} roots The roots of the executed plans.
   */
  show(roots) {
    const document = this.panel.element.ownerDocument;
    if (roots.length === 0) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.textContent = 'This scene has no recorded plan.';
      this.panel.element.replaceChildren(empty);
      return;
    }
    const tree = document.createElement('ul');
    tree.className = 'plan-tree';
    tree.append(...roots.map((node) => this.#item(node)));
    this.panel.element.replaceChildren(tree);
  }

  /**
   * Show the plan a live publisher executes, its nodes listed flat with their parents.
   * @param {Object} plan A live plan.
   */
  showLive(plan) {
    this.show(planTreesOf(plan[LivePlanKey.NODES] ?? []));
  }

  /**
   * @param {Object} node A plan node.
   * @returns {HTMLElement} The node with its children.
   */
  #item(node) {
    const document = this.panel.element.ownerDocument;
    const item = document.createElement('li');
    const row = document.createElement('div');
    row.className = 'plan-node';
    row.dataset.status = node[PlanNodeKey.STATUS];
    const label = document.createElement('span');
    label.textContent = node[PlanNodeKey.LABEL];
    const kind = document.createElement('span');
    kind.className = 'kind';
    kind.textContent = node[PlanNodeKey.KIND];
    const status = document.createElement('span');
    status.className = 'status';
    status.textContent = node[PlanNodeKey.STATUS];
    row.append(label, kind, status);
    item.append(row);
    const children = node[PlanNodeKey.CHILDREN] ?? [];
    if (children.length) {
      const list = document.createElement('ul');
      list.append(...children.map((child) => this.#item(child)));
      item.append(list);
    }
    return item;
  }
}

// %% live plans

/**
 * @param {Array<Object>} nodes The nodes of a live plan, each naming its parent.
 * @returns {Array<Object>} The same nodes as plan trees, children in the order listed.
 */
export function planTreesOf(nodes) {
  const trees = new Map(
    nodes.map((node) => [
      node[LivePlanNodeKey.IDENTIFIER],
      {
        [PlanNodeKey.IDENTIFIER]: node[LivePlanNodeKey.IDENTIFIER],
        [PlanNodeKey.KIND]: node[LivePlanNodeKey.KIND],
        [PlanNodeKey.LABEL]: node[LivePlanNodeKey.LABEL],
        [PlanNodeKey.STATUS]: node[LivePlanNodeKey.STATUS],
        [PlanNodeKey.CHILDREN]: [],
      },
    ]),
  );
  const roots = [];
  for (const node of nodes) {
    const tree = trees.get(node[LivePlanNodeKey.IDENTIFIER]);
    const parent = trees.get(node[LivePlanNodeKey.PARENT]);
    if (parent) parent[PlanNodeKey.CHILDREN].push(tree);
    else roots.push(tree);
  }
  return roots;
}
