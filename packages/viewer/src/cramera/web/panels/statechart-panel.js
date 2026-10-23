/**
 * The motion statechart a recorded run was ticking at the shown frame: its nodes as a
 * tree, each with the life-cycle and observation state the recording stored.
 */

import { ChartKey, ChartNodeKey, LiveChartNodeKey, LiveStatechartKey, MomentKey, StatechartsKey } from '../protocol.js';
import { SidePanel } from './panel-host.js';

/**
 * The moment position of a frame without a chart state.
 */
const NO_MOMENT = -1;

// %% panel

export class StatechartPanel {
  /**
   * The panel.
   * @type {SidePanel}
   */
  panel;

  /**
   * The recording's statecharts, or null.
   * @type {Object|null}
   */
  #statecharts = null;

  /**
   * The moment shown, to skip redrawing an unchanged state.
   * @type {number|null}
   */
  #shownMoment = null;

  /**
   * @param {Document} document The page.
   */
  constructor(document) {
    this.panel = new SidePanel('statechart', 'Chart states', document.createElement('section'));
  }

  /**
   * @param {Object|null} statecharts The recording's statecharts document, or null.
   */
  show(statecharts) {
    this.#statecharts = statecharts;
    this.#shownMoment = null;
    this.showFrame(0);
  }

  /**
   * @param {number} frame The shown frame.
   */
  showFrame(frame) {
    const moment = this.#statecharts?.[StatechartsKey.FRAMES]?.[frame] ?? NO_MOMENT;
    if (moment === this.#shownMoment) return;
    this.#shownMoment = moment;
    if (!this.#statecharts) {
      this.#message('This scene has no recorded statecharts.');
      return;
    }
    if (moment === NO_MOMENT) {
      this.#message('No motion statechart runs at this frame.');
      return;
    }
    const state = this.#statecharts[StatechartsKey.MOMENTS][moment];
    const chart = this.#statecharts[StatechartsKey.CHARTS][state[MomentKey.CHART]];
    const title = this.panel.element.ownerDocument.createElement('h2');
    title.textContent = chart[ChartKey.TITLE];
    this.panel.element.replaceChildren(title, this.#tree(chart, state));
  }

  /**
   * Show the statechart a live publisher ticks, with each node's current states.
   * @param {Object} chart A live statechart.
   */
  showLive(chart) {
    const nodes = chart[LiveStatechartKey.NODES] ?? [];
    this.#statecharts = null;
    this.#shownMoment = null;
    if (nodes.length === 0) {
      this.#message('No motion statechart runs.');
      return;
    }
    const title = this.panel.element.ownerDocument.createElement('h2');
    title.textContent = chart[LiveStatechartKey.TITLE];
    const structure = {
      [ChartKey.NODES]: nodes.map((node) => ({
        [ChartNodeKey.IDENTIFIER]: node[LiveChartNodeKey.IDENTIFIER],
        [ChartNodeKey.NAME]: node[LiveChartNodeKey.NAME],
        [ChartNodeKey.PARENT]: node[LiveChartNodeKey.PARENT] ?? null,
      })),
    };
    const state = {
      [MomentKey.LIFE_CYCLES]: nodes.map((node) => node[LiveChartNodeKey.LIFE_CYCLE]),
      [MomentKey.OBSERVATIONS]: nodes.map((node) => node[LiveChartNodeKey.OBSERVATION]),
    };
    this.panel.element.replaceChildren(title, this.#tree(structure, state));
  }

  /**
   * @param {Object} chart A chart.
   * @param {Object} state The chart's state at one moment.
   * @returns {HTMLElement} The chart's nodes as a tree under their parents.
   */
  #tree(chart, state) {
    const document = this.panel.element.ownerDocument;
    const nodes = chart[ChartKey.NODES];
    const childrenOf = (parent) => nodes.map((node, position) => [node, position]).filter(([node]) => (node[ChartNodeKey.PARENT] ?? null) === parent);
    const list = (parent) => {
      const items = childrenOf(parent).map(([node, position]) => {
        const item = document.createElement('li');
        const row = document.createElement('div');
        row.className = 'chart-node';
        const lifeCycle = state[MomentKey.LIFE_CYCLES][position];
        row.dataset.lifeCycle = lifeCycle;
        const name = document.createElement('span');
        name.textContent = node[ChartNodeKey.NAME];
        const states = document.createElement('span');
        states.className = 'status';
        states.textContent = `${lifeCycle} · ${state[MomentKey.OBSERVATIONS][position]}`;
        row.append(name, states);
        item.append(row);
        const below = list(node[ChartNodeKey.IDENTIFIER]);
        if (below.children.length) item.append(below);
        return item;
      });
      const element = document.createElement('ul');
      element.append(...items);
      return element;
    };
    const tree = list(null);
    tree.className = 'plan-tree';
    return tree;
  }

  /**
   * @param {string} text What the panel says instead of a chart.
   */
  #message(text) {
    const message = this.panel.element.ownerDocument.createElement('p');
    message.className = 'empty';
    message.textContent = text;
    this.panel.element.replaceChildren(message);
  }
}
