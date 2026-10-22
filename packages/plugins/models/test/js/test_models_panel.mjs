import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { PanelHost } from '../../../panels/panel-host.js';
import { FigureKey, ModelAnswerKey, ModelVariableKey, PluginName, VariableKind, WorkbenchStateKey } from '../../../protocol.js';
import { register } from '../index.js';
import { ModelsPanel } from '../models-panel.js';
import { PlotlyLoader, PlotlyUnavailable } from '../plotly-loader.js';
import { FakeClient, FakePlotly, FakePlotlyLoader, refused } from './fakes.mjs';
import { FakeDocument } from './support/fake-document.mjs';

/**
 * The workbench state of the tests.
 */
const STATE = JSON.parse(readFileSync(new URL('./workbench_state.json', import.meta.url), 'utf-8'));

/**
 * The tests' variables.
 */
const VARIABLES = STATE[WorkbenchStateKey.VARIABLES];

/**
 * @param {Object} element An element.
 * @param {string} tagName A tag.
 * @returns {Array<Object>} Its descendants of that tag.
 */
function tagged(element, tagName) {
  return element.findAll((child) => child.tagName === tagName);
}

/**
 * A panel over a fake workbench and a fake Plotly.
 */
class PanelSetup {
  /**
   * @param {Object} state The workbench state.
   */
  constructor(state) {
    this.document = new FakeDocument();
    this.client = new FakeClient(state);
    this.plotly = new FakePlotly();
    this.panel = new ModelsPanel(this.document, this.client, new FakePlotlyLoader(this.plotly));
  }
}

// %% state

test('the loaded model and its variables are shown with the questions', async () => {
  const setup = new PanelSetup(STATE);
  await setup.panel.refresh();
  assert.match(setup.panel.status.textContent, new RegExp(STATE[WorkbenchStateKey.NAME]));
  assert.equal(tagged(setup.panel.panel.element, 'LI').length, VARIABLES.length);
  assert.equal(setup.panel.sections.mode.element.hidden, false);
});

test('without a model the questions are hidden', async () => {
  const setup = new PanelSetup({ [WorkbenchStateKey.LOADED]: false, [WorkbenchStateKey.VARIABLES]: [] });
  await setup.panel.refresh();
  assert.equal(setup.panel.sections.probability.element.hidden, true);
});

test('a workbench without its libraries shows why and offers nothing', async () => {
  const setup = new PanelSetup(STATE);
  const reason = 'The models workbench needs plotly.';
  setup.client.failure = refused(503, reason);
  await setup.panel.refresh();
  assert.equal(setup.panel.status.textContent, reason);
  assert.equal(setup.panel.fileInput.hidden, true);
  assert.equal(setup.panel.sections.posterior.element.hidden, true);
});

test('a chosen file is loaded as its name and its text', async () => {
  const setup = new PanelSetup(STATE);
  await setup.panel.load({ name: 'circuit.json', text: async () => '{"a": 1}' });
  assert.deepEqual(setup.client.asked, [['load', 'circuit.json', '{"a": 1}']]);
  assert.match(setup.panel.status.textContent, new RegExp(STATE[WorkbenchStateKey.NAME]));
});

test('a file the workbench refuses is reported', async () => {
  const setup = new PanelSetup(STATE);
  setup.client.failure = refused(400, 'not a circuit');
  await setup.panel.load({ name: 'circuit.json', text: async () => '[]' });
  assert.match(setup.panel.status.textContent, /not a circuit/);
});

test('the file choice loads its file and is emptied again', async () => {
  const setup = new PanelSetup(STATE);
  setup.panel.fileInput.files = [{ name: 'chosen.json', text: async () => '{}' }];
  setup.panel.fileInput.dispatch('change');
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(setup.client.asked[0][1], 'chosen.json');
  assert.equal(setup.panel.fileInput.value, '');
});

// %% questions

test('the probability question sends its rows and shows the answer', async () => {
  const setup = new PanelSetup(STATE);
  await setup.panel.refresh();
  const row = setup.panel.query.add();
  row.choose(VARIABLES.find((variable) => variable[ModelVariableKey.KIND] === VariableKind.CONTINUOUS));
  setup.client.answers.probability = { [ModelAnswerKey.PROBABILITY]: 0.25 };
  setup.panel.sections.probability.button.dispatch('click');
  await new Promise((resolve) => setImmediate(resolve));
  const [, query, evidence] = setup.client.asked[0];
  assert.deepEqual(query, setup.panel.query.constraints());
  assert.deepEqual(evidence, []);
  assert.match(setup.panel.sections.probability.answer.innerText, /0\.250000/);
});

test('the posterior needs a chosen variable', async () => {
  const setup = new PanelSetup(STATE);
  await setup.panel.refresh();
  await setup.panel.askPosterior();
  assert.deepEqual(setup.client.asked, []);
  assert.notEqual(setup.panel.sections.posterior.answer.innerText, '');
});

test('each chosen variable is plotted from its figure', async () => {
  const setup = new PanelSetup(STATE);
  await setup.panel.refresh();
  const boxes = tagged(setup.panel.sections.posterior.element, 'INPUT').filter((input) => input.type === 'checkbox');
  boxes[0].checked = true;
  const figure = { [FigureKey.DATA]: [{ type: 'bar' }], [FigureKey.LAYOUT]: { title: 'color' } };
  setup.client.answers.posterior = { [ModelAnswerKey.FIGURES]: { [boxes[0].value]: figure } };
  await setup.panel.askPosterior();
  assert.deepEqual(setup.client.asked[0][1], [boxes[0].value]);
  assert.equal(setup.plotly.plots.length, 1);
  assert.deepEqual(setup.plotly.plots[0].data, figure[FigureKey.DATA]);
});

test('the mode is shown as one table per assignment with its likelihood', async () => {
  const setup = new PanelSetup(STATE);
  await setup.panel.refresh();
  const modes = [{ color: 'red', x: '[0, 1]' }, { color: 'blue', x: '0.5' }];
  setup.client.answers.mode = { [ModelAnswerKey.LIKELIHOOD]: 0.35, [ModelAnswerKey.MODES]: modes };
  await setup.panel.askMode();
  const tables = tagged(setup.panel.sections.mode.answer, 'TABLE');
  assert.equal(tables.length, modes.length);
  assert.equal(tagged(tables[1], 'TD')[0].textContent, modes[1].color);
});

test('a refused question shows the reason', async () => {
  const setup = new PanelSetup(STATE);
  await setup.panel.refresh();
  setup.client.failure = refused(422, 'impossible evidence');
  await setup.panel.askMode();
  assert.match(setup.panel.sections.mode.answer.innerText, /impossible evidence/);
});

test('an answer about a model replaced meanwhile is dropped', async () => {
  const setup = new PanelSetup(STATE);
  await setup.panel.refresh();
  let answer;
  setup.client.mode = () => new Promise((resolve) => (answer = resolve));
  const asked = setup.panel.askMode();
  await setup.panel.refresh();
  answer({ [ModelAnswerKey.LIKELIHOOD]: 1, [ModelAnswerKey.MODES]: [{ x: '1' }] });
  await asked;
  assert.equal(tagged(setup.panel.sections.mode.answer, 'TABLE').length, 0);
});

// %% plotting library

test('Plotly is loaded once by a script element and handed out from the page', async () => {
  const document = new FakeDocument();
  document.head = document.createElement('head');
  document.defaultView = { Plotly: new FakePlotly() };
  const loader = new PlotlyLoader(document, 'vendor/plotly.js');
  const first = loader.load();
  const second = loader.load();
  const [script] = document.head.children;
  assert.equal(document.head.children.length, 1);
  script.dispatch('load');
  assert.equal(await first, document.defaultView.Plotly);
  assert.equal(await second, document.defaultView.Plotly);
});

test('a bundle that fails to load is reported and tried again', async () => {
  const document = new FakeDocument();
  document.head = document.createElement('head');
  const loader = new PlotlyLoader(document, 'vendor/plotly.js');
  const failed = loader.load();
  document.head.children[0].dispatch('error');
  await assert.rejects(failed, PlotlyUnavailable);
  assert.equal(document.head.children.length, 0);
  loader.load();
  assert.equal(document.head.children.length, 1);
});

// %% registration

test('registration adds the stylesheet and the Models panel', async () => {
  const document = new FakeDocument();
  document.head = document.createElement('head');
  const panels = new PanelHost(document.createElement('aside'));
  globalThis.fetch = async () => ({ ok: true, json: async () => STATE });
  const panel = register({ bus: null, panels, api: { url: (route) => `http://127.0.0.1${route}` }, view: null }, document);
  assert.deepEqual(panels.identifiers(), [PluginName.MODELS]);
  assert.equal(document.head.children[0].rel, 'stylesheet');
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(panel.status.textContent, new RegExp(STATE[WorkbenchStateKey.NAME]));
});
