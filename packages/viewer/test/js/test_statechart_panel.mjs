import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { StatechartPanel } from '../../src/cramera/web/panels/statechart-panel.js';
import { ChartKey, ChartNodeKey, MomentKey, StatechartsKey } from '../../src/cramera/web/protocol.js';
import { FakeDocument } from './support/fake-document.mjs';

const STATECHARTS = JSON.parse(readFileSync(new URL('../../../protocol/test/dataset/statecharts_excerpt.json', import.meta.url), 'utf8'));

test('a frame shows the chart of its moment with each node\'s recorded states', () => {
  const panel = new StatechartPanel(new FakeDocument());
  panel.show(STATECHARTS);
  const frame = STATECHARTS[StatechartsKey.FRAMES].findIndex((moment) => moment >= 0);
  panel.showFrame(frame);
  const moment = STATECHARTS[StatechartsKey.MOMENTS][STATECHARTS[StatechartsKey.FRAMES][frame]];
  const chart = STATECHARTS[StatechartsKey.CHARTS][moment[MomentKey.CHART]];
  const element = panel.panel.element;
  assert.equal(element.children[0].textContent, chart[ChartKey.TITLE]);
  const rows = element.findAll((child) => child.className === 'chart-node');
  assert.equal(rows.length, chart[ChartKey.NODES].length);
  const first = chart[ChartKey.NODES].findIndex((node) => (node[ChartNodeKey.PARENT] ?? null) === null);
  assert.equal(rows[0].dataset.lifeCycle, moment[MomentKey.LIFE_CYCLES][first]);
});

test('a frame without a chart state and a scene without statecharts say so', () => {
  const panel = new StatechartPanel(new FakeDocument());
  panel.show(STATECHARTS);
  assert.match(panel.panel.element.innerText, /No motion statechart runs at this frame/);
  panel.show(null);
  assert.match(panel.panel.element.innerText, /no recorded statecharts/);
});
