/**
 * The Models side panel: load a probabilistic circuit and ask it for the probability
 * of an event, the posterior marginals of variables and the most likely assignments,
 * each given evidence.
 */

import { SidePanel } from '../../panels/panel-host.js';
import {
  FigureKey,
  ModelAnswerKey,
  ModelVariableKey,
  PluginName,
  VariableKind,
  WorkbenchStateKey,
} from '../../protocol.js';
import { ConstraintRows } from './constraint-rows.js';

/**
 * How many decimal places a probability is shown with.
 */
const PROBABILITY_DECIMALS = 6;

/**
 * How many decimal places of the mantissa a likelihood is shown with.
 */
const LIKELIHOOD_DIGITS = 4;

/**
 * The options every posterior plot is drawn with: it follows the panel's width and
 * has no tool bar, which would cover its title in the narrow panel.
 */
const PLOT_OPTIONS = Object.freeze({ responsive: true, displayModeBar: false });

/**
 * What a posterior plot changes in its figure's layout to fit the narrow panel: the
 * legend below the plot, small margins and the panel's background.
 */
const PANEL_LAYOUT = Object.freeze({
  legend: { orientation: 'h', y: -0.35 },
  margin: { l: 40, r: 10, t: 40, b: 40 },
  paper_bgcolor: 'rgba(0, 0, 0, 0)',
});

/**
 * The file types the file choice offers.
 */
const CIRCUIT_FILES = '.json,application/json';

// %% sections

/**
 * One question of the panel: its heading, its inputs, its button and its answer.
 */
class QuestionSection {
  /**
   * The section's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * Where the answer is shown.
   * @type {HTMLElement}
   */
  answer;

  /**
   * The button asking the question.
   * @type {HTMLButtonElement}
   */
  button;

  /**
   * @param {Document} document The page.
   * @param {string} title The question's heading.
   * @param {string} action The button's text.
   * @param {Array<HTMLElement>} inputs The question's inputs, in order.
   */
  constructor(document, title, action, inputs) {
    this.element = document.createElement('section');
    this.element.className = 'models-question';
    const heading = document.createElement('h2');
    heading.textContent = title;
    this.button = document.createElement('button');
    this.button.type = 'button';
    this.button.className = 'primary';
    this.button.textContent = action;
    this.answer = document.createElement('div');
    this.answer.className = 'models-answer';
    this.element.append(heading, ...inputs, this.button, this.answer);
  }

  /**
   * @param {string} message A message instead of an answer.
   * @param {boolean} failed Whether it reports a failure.
   */
  say(message, failed) {
    const text = this.answer.ownerDocument.createElement('p');
    text.className = failed ? 'models-error' : 'models-note';
    text.textContent = message;
    this.answer.replaceChildren(text);
  }
}

// %% panel

export class ModelsPanel {
  /**
   * The side panel.
   * @type {SidePanel}
   */
  panel;

  /**
   * The page.
   * @type {Document}
   */
  #document;

  /**
   * The workbench routes.
   * @type {import('./models-client.js').ModelsClient}
   */
  #client;

  /**
   * Loads Plotly for the posterior plots.
   * @type {import('./plotly-loader.js').PlotlyLoader}
   */
  #plotly;

  /**
   * What the workbench holds, or why it cannot answer.
   * @type {HTMLElement}
   */
  status;

  /**
   * The loaded model's variables.
   * @type {HTMLElement}
   */
  #variableList;

  /**
   * The file choice.
   * @type {HTMLInputElement}
   */
  fileInput;

  /**
   * The query of the probability question.
   * @type {ConstraintRows}
   */
  query;

  /**
   * The evidence of each question.
   * @type {{probability: ConstraintRows, posterior: ConstraintRows, mode: ConstraintRows}}
   */
  evidence;

  /**
   * The checkboxes choosing the posterior's variables.
   * @type {Array<HTMLInputElement>}
   */
  #posteriorChoices = [];

  /**
   * The element holding those checkboxes.
   * @type {HTMLElement}
   */
  #posteriorVariables;

  /**
   * The questions' sections.
   * @type {{probability: QuestionSection, posterior: QuestionSection, mode: QuestionSection}}
   */
  sections;

  /**
   * Counts loaded models, so answers about an earlier model are dropped.
   * @type {number}
   */
  #generation = 0;

  /**
   * @param {Document} document The page.
   * @param {import('./models-client.js').ModelsClient} client The workbench routes.
   * @param {import('./plotly-loader.js').PlotlyLoader} plotly Loads Plotly.
   */
  constructor(document, client, plotly) {
    this.#document = document;
    this.#client = client;
    this.#plotly = plotly;
    const element = document.createElement('section');
    element.className = 'models-panel';
    this.panel = new SidePanel(PluginName.MODELS, 'Models', element);
    this.status = document.createElement('p');
    this.status.className = 'models-status';
    this.fileInput = document.createElement('input');
    this.fileInput.type = 'file';
    this.fileInput.accept = CIRCUIT_FILES;
    this.fileInput.addEventListener('change', () => this.#loadChosenFile());
    this.#variableList = document.createElement('ul');
    this.#variableList.className = 'models-variables';
    this.query = new ConstraintRows(document, 'Query');
    this.evidence = {
      probability: new ConstraintRows(document, 'Evidence'),
      posterior: new ConstraintRows(document, 'Evidence'),
      mode: new ConstraintRows(document, 'Evidence'),
    };
    this.#posteriorVariables = document.createElement('div');
    this.#posteriorVariables.className = 'models-choices';
    this.sections = {
      probability: new QuestionSection(document, 'Probability', 'Calculate', [this.query.element, this.evidence.probability.element]),
      posterior: new QuestionSection(document, 'Posterior', 'Plot', [this.#posteriorVariables, this.evidence.posterior.element]),
      mode: new QuestionSection(document, 'Mode', 'Find', [this.evidence.mode.element]),
    };
    this.sections.probability.button.addEventListener('click', () => this.askProbability());
    this.sections.posterior.button.addEventListener('click', () => this.askPosterior());
    this.sections.mode.button.addEventListener('click', () => this.askMode());
    element.append(this.status, this.fileInput, this.#variableList, ...Object.values(this.sections).map((section) => section.element));
    this.#show({ [WorkbenchStateKey.LOADED]: false, [WorkbenchStateKey.VARIABLES]: [] });
  }

  /**
   * Ask the workbench what it holds and show it.
   * @returns {Promise<void>} Settles once the state or the reason it is unavailable is shown.
   */
  async refresh() {
    await this.#client.state().then(
      (state) => this.#show(state),
      (error) => this.#unavailable(error.reason ?? error.message),
    );
  }

  /**
   * Load a model file.
   * @param {{name: string, text: function(): Promise<string>}} file The chosen file.
   * @returns {Promise<void>} Settles once the new state or the failure is shown.
   */
  async load(file) {
    this.status.textContent = `Loading ${file.name}…`;
    const text = await file.text();
    await this.#client.load(file.name, text).then(
      (state) => this.#show(state),
      (error) => this.#failed(`Could not load ${file.name}: ${error.reason ?? error.message}`),
    );
  }

  /**
   * Ask for the probability of the query given the evidence.
   * @returns {Promise<void>} Settles once the answer is shown or dropped.
   */
  askProbability() {
    const section = this.sections.probability;
    return this.#ask(section, this.#client.probability(this.query.constraints(), this.evidence.probability.constraints()), (answer) => {
      const value = this.#document.createElement('p');
      value.className = 'models-value';
      value.textContent = `P = ${answer[ModelAnswerKey.PROBABILITY].toFixed(PROBABILITY_DECIMALS)}`;
      section.answer.replaceChildren(value);
    });
  }

  /**
   * Plot the posterior marginals of the chosen variables given the evidence.
   * @returns {Promise<void>} Settles once the plots or a message are shown.
   */
  async askPosterior() {
    const section = this.sections.posterior;
    const chosen = this.#posteriorChoices.filter((box) => box.checked).map((box) => box.value);
    if (!chosen.length) {
      section.say('Choose at least one variable.', true);
      return;
    }
    await this.#ask(section, this.#client.posterior(chosen, this.evidence.posterior.constraints()), async (answer) => {
      const Plotly = await this.#plotly.load();
      section.answer.replaceChildren();
      for (const name of chosen) {
        const figure = answer[ModelAnswerKey.FIGURES][name];
        const card = this.#document.createElement('div');
        card.className = 'models-plot';
        section.answer.append(card);
        await Plotly.newPlot(card, figure[FigureKey.DATA], { ...figure[FigureKey.LAYOUT], ...PANEL_LAYOUT }, PLOT_OPTIONS);
      }
    });
  }

  /**
   * Find the most likely assignments given the evidence.
   * @returns {Promise<void>} Settles once the answer is shown or dropped.
   */
  askMode() {
    const section = this.sections.mode;
    return this.#ask(section, this.#client.mode(this.evidence.mode.constraints()), (answer) => {
      const likelihood = this.#document.createElement('p');
      likelihood.className = 'models-value';
      likelihood.textContent = `Likelihood ${answer[ModelAnswerKey.LIKELIHOOD].toExponential(LIKELIHOOD_DIGITS)}`;
      const modes = answer[ModelAnswerKey.MODES].map((mode) => this.#modeTable(mode));
      section.answer.replaceChildren(likelihood, ...modes);
    });
  }

  /**
   * Show an answer unless a newer model was loaded meanwhile, or the failure.
   * @param {QuestionSection} section The question's section.
   * @param {Promise<Object>} asked The answer.
   * @param {function(Object): (void|Promise<void>)} show Shows the answer.
   * @returns {Promise<void>} Settles once the answer or the failure is shown or dropped.
   */
  async #ask(section, asked, show) {
    const generation = this.#generation;
    section.say('Calculating…', false);
    await asked.then(
      (answer) => (generation === this.#generation ? show(answer) : undefined),
      (error) => (generation === this.#generation ? section.say(error.reason ?? error.message, true) : undefined),
    ).catch((error) => section.say(error.message, true));
  }

  /**
   * @param {Object} mode One most likely assignment: each variable's values as text.
   * @returns {HTMLElement} The assignment as a table.
   */
  #modeTable(mode) {
    const table = this.#document.createElement('table');
    table.className = 'models-mode';
    for (const [name, value] of Object.entries(mode)) {
      const row = this.#document.createElement('tr');
      const variable = this.#document.createElement('th');
      variable.textContent = name;
      const values = this.#document.createElement('td');
      values.textContent = value;
      row.append(variable, values);
      table.append(row);
    }
    return table;
  }

  /**
   * Load the file the file choice holds.
   */
  #loadChosenFile() {
    const file = this.fileInput.files?.[0];
    if (file) this.load(file);
    this.fileInput.value = '';
  }

  /**
   * @param {Object} state The workbench state.
   */
  #show(state) {
    this.#generation += 1;
    const variables = state[WorkbenchStateKey.VARIABLES] ?? [];
    this.status.className = 'models-status';
    this.status.textContent = state[WorkbenchStateKey.LOADED]
      ? `${state[WorkbenchStateKey.NAME]} · ${variables.length} variables`
      : 'Load a probabilistic circuit (.json) to begin.';
    this.fileInput.hidden = false;
    this.#variableList.replaceChildren(...variables.map((variable) => this.#variableItem(variable)));
    this.query.setVariables(variables);
    for (const rows of Object.values(this.evidence)) rows.setVariables(variables);
    this.#posteriorChoices = variables.map((variable) => this.#posteriorChoice(variable));
    this.#posteriorVariables.replaceChildren(...this.#posteriorChoices.map((box) => box.parentElement));
    for (const section of Object.values(this.sections)) {
      section.element.hidden = !state[WorkbenchStateKey.LOADED];
      section.answer.replaceChildren();
    }
  }

  /**
   * @param {string} reason Why the workbench cannot answer.
   */
  #unavailable(reason) {
    this.#failed(reason);
    this.fileInput.hidden = true;
    for (const section of Object.values(this.sections)) section.element.hidden = true;
  }

  /**
   * @param {string} message What went wrong.
   */
  #failed(message) {
    this.status.className = 'models-status models-error';
    this.status.textContent = message;
  }

  /**
   * @param {Object} variable A variable of the workbench state.
   * @returns {HTMLElement} The variable's list item: its name and its values or kind.
   */
  #variableItem(variable) {
    const item = this.#document.createElement('li');
    const name = this.#document.createElement('b');
    name.textContent = variable[ModelVariableKey.NAME];
    const domain = this.#document.createElement('span');
    domain.textContent =
      variable[ModelVariableKey.KIND] === VariableKind.SYMBOLIC
        ? ` {${variable[ModelVariableKey.VALUES].join(', ')}}`
        : ` ${variable[ModelVariableKey.KIND]} in [${variable[ModelVariableKey.LOW]}, ${variable[ModelVariableKey.HIGH]}]`;
    item.append(name, domain);
    return item;
  }

  /**
   * @param {Object} variable A variable of the workbench state.
   * @returns {HTMLInputElement} Its checkbox, inside its label.
   */
  #posteriorChoice(variable) {
    const label = this.#document.createElement('label');
    const box = this.#document.createElement('input');
    box.type = 'checkbox';
    box.value = variable[ModelVariableKey.NAME];
    const text = this.#document.createElement('span');
    text.textContent = variable[ModelVariableKey.NAME];
    label.append(box, text);
    return box;
  }
}
