/**
 * Where the plan runs and who performs it: the environment the robots start in, the
 * plan's robots as a list whose entry chosen is the robot whose plan is edited, that
 * robot's model, name and start pose, and adding and removing robots.
 */

import { IndexEntryKey, PlanBuilderCatalogKey, PlanKey, PlannedRobotKey, RobotModelKey } from '../../../protocol.js';
import { Elements, PlanAction } from './elements.js';
import { PlanPose } from './poses.js';

/**
 * The environment choice of an empty floor.
 */
export const EMPTY_FLOOR = Object.freeze({ value: '', label: 'Empty floor' });

/**
 * What the environment section says about each kind of choice.
 */
export const EnvironmentNote = Object.freeze({
  EMPTY_FLOOR: 'The robots start on an empty floor.',
  NONE_OFFERED:
    'No environment is offered yet. An environment is a scene without a robot, such as one made in the Scene Builder or imported from a USD stage; the robots start on an empty floor until one is there.',
  /**
   * @param {string} label The environment's name for people.
   * @returns {string} What the section says about a chosen environment.
   */
  chosen: (label) => `The robots start in ${label}; place them and the objects in the 3D view.`,
});

// %% environment

export class EnvironmentView {
  /**
   * The view's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * The environment choices, the empty floor first.
   * @type {Array<{value: string, label: string}>}
   */
  #choices;

  /**
   * The page that applies the person's edits.
   * @type {Object}
   */
  #editor;

  /**
   * The environment select.
   * @type {HTMLSelectElement}
   */
  select;

  /**
   * The line saying what the chosen environment means.
   * @type {HTMLElement}
   */
  #note;

  /**
   * Owns the select's listener.
   * @type {Elements}
   */
  #elements;

  /**
   * @param {Document} document The page's document.
   * @param {Object} editor The page: `state` (the `PlanState`) and `edit(change)`.
   */
  constructor(document, editor) {
    this.#editor = editor;
    this.#elements = new Elements(document);
    const elements = this.#elements;
    const state = editor.state;
    this.#choices = [
      EMPTY_FLOOR,
      ...state.catalog[PlanBuilderCatalogKey.ENVIRONMENTS].map((entry) => ({ value: entry[IndexEntryKey.NAME], label: entry[IndexEntryKey.ENVIRONMENT] ?? entry[IndexEntryKey.NAME] })),
    ];
    this.select = elements.select(PlanAction.ENVIRONMENT, this.#choices, state.field(PlanKey.ENVIRONMENT), (value) =>
      this.#editor.edit(() => this.#editor.state.setField(PlanKey.ENVIRONMENT, value || null)),
    );
    this.#note = elements.create('p', 'muted environment-note');
    this.element = elements.create('div', 'environment');
    this.element.append(this.select, this.#note);
  }

  /**
   * Show the chosen environment and what it means.
   */
  render() {
    const chosen = this.#editor.state.field(PlanKey.ENVIRONMENT) || '';
    this.select.value = chosen;
    this.#note.textContent = this.note(chosen);
  }

  /**
   * @param {string} chosen The chosen environment's name, or '' for the empty floor.
   * @returns {string} What the choice means.
   */
  note(chosen) {
    if (this.#choices.length === 1) return EnvironmentNote.NONE_OFFERED;
    const choice = this.#choices.find((candidate) => candidate.value === chosen);
    return chosen && choice ? EnvironmentNote.chosen(choice.label) : EnvironmentNote.EMPTY_FLOOR;
  }

  /**
   * Remove every listener.
   */
  dispose() {
    this.#elements.dispose();
  }
}

// %% robots

export class RobotsView {
  /**
   * The view's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * The page that applies the person's edits.
   * @type {Object}
   */
  #editor;

  /**
   * Owns the listeners of the shown controls, replaced on every render.
   * @type {Elements}
   */
  #shown;

  /**
   * The model a robot is added as.
   * @type {string|null}
   */
  #addedModel = null;

  /**
   * @param {Document} document The page's document.
   * @param {Object} editor The page: `state` (the `PlanState`) and `edit(change)`.
   */
  constructor(document, editor) {
    this.#editor = editor;
    this.#shown = new Elements(document);
    this.element = this.#shown.create('div', 'robots');
  }

  /**
   * Show the robots, which one's plan is edited, and the edited robot's settings.
   */
  render() {
    const document = this.#shown.document;
    this.#shown.dispose();
    const elements = (this.#shown = new Elements(document));
    const state = this.#editor.state;
    const robot = state.activeRobot();
    const models = state.catalog[PlanBuilderCatalogKey.ROBOTS].map((model) => ({ value: model[RobotModelKey.NAME], label: model[RobotModelKey.LABEL] || model[RobotModelKey.NAME] }));
    if (!robot) {
      this.element.replaceChildren(elements.create('p', 'empty', 'The CRAM workspace offers no robot here.'));
      return;
    }
    const identifier = robot[PlannedRobotKey.IDENTIFIER];
    const list = elements.create('ul', 'robot-list');
    list.append(...state.robots().map((entry) => this.#entry(elements, entry, entry === robot)));
    const label = elements.input('text', PlanAction.ROBOT_LABEL, () => this.#editor.edit(() => state.setRobotLabel(identifier, label.value)));
    label.value = robot[PlannedRobotKey.LABEL];
    const model = elements.select(PlanAction.ROBOT_MODEL, models, robot[PlannedRobotKey.MODEL], (value) => this.#editor.edit(() => state.setRobotModel(identifier, value)));
    const pose = robot[PlannedRobotKey.POSE];
    const [x, y] = PlanPose.position(pose);
    const place = (position, yaw) => this.#editor.edit(() => state.setRobotPose(identifier, PlanPose.of(...position, yaw)));
    const row = elements.create('div', 'pose-row');
    row.append(
      elements.number('x', x, PlanAction.POSE, (value) => place([value, y, 0], PlanPose.yaw(pose))),
      elements.number('y', y, PlanAction.POSE, (value) => place([x, value, 0], PlanPose.yaw(pose))),
      elements.number('yaw°', PlanPose.degrees(PlanPose.yaw(pose)), PlanAction.POSE, (value) => place([x, y, 0], PlanPose.radians(value))),
    );
    const remove = elements.button(`Remove ${robot[PlannedRobotKey.LABEL]}`, PlanAction.REMOVE_ROBOT, () => this.#editor.edit(() => state.removeRobot(identifier)));
    remove.disabled = state.robots().length <= 1;
    remove.title = remove.disabled ? 'A plan keeps at least one robot.' : '';
    const settings = elements.create('div', 'robot-settings');
    settings.append(
      elements.create('h3', '', `Settings of ${robot[PlannedRobotKey.LABEL]}`),
      elements.label('name', label),
      elements.label('model', model),
      elements.label('starts at', row),
      remove,
    );
    const addedModel = elements.select(PlanAction.ROBOT_MODEL, models, this.#addedModel ?? robot[PlannedRobotKey.MODEL], (value) => {
      this.#addedModel = value;
    });
    const adding = elements.create('div', 'button-row');
    adding.append(
      addedModel,
      elements.button('Add', PlanAction.ADD_ROBOT, () => this.#editor.edit(() => state.addRobot(addedModel.value))),
    );
    this.element.replaceChildren(list, settings, elements.label('add a robot', adding, 'robot-adding'));
  }

  /**
   * @param {Elements} elements Owns the entry's listener.
   * @param {Object} robot A robot of the plan.
   * @param {boolean} edited Whether its plan is the one edited.
   * @returns {HTMLElement} The robot's entry, choosing its plan when clicked.
   */
  #entry(elements, robot, edited) {
    const identifier = robot[PlannedRobotKey.IDENTIFIER];
    const button = elements.button('', PlanAction.SELECT_ROBOT, () => this.#editor.edit(() => this.#editor.state.selectRobot(identifier)));
    button.dataset.robot = identifier;
    button.setAttribute('aria-pressed', String(edited));
    const [x, y] = PlanPose.position(robot[PlannedRobotKey.POSE]);
    const steps = robot[PlannedRobotKey.STEPS].length;
    const head = elements.create('span', 'robot-head');
    head.append(elements.create('strong', '', robot[PlannedRobotKey.LABEL]), elements.create('span', 'badge', this.#editor.state.modelLabel(robot[PlannedRobotKey.MODEL])));
    const facts = `${steps} ${steps === 1 ? 'step' : 'steps'} · starts at ${RobotsView.metres(x)}, ${RobotsView.metres(y)} m`;
    button.append(head, elements.create('span', 'robot-facts', facts));
    if (edited) button.append(elements.create('span', 'robot-editing', 'editing its plan'));
    const item = elements.create('li');
    item.append(button);
    return item;
  }

  /**
   * @param {number} value A coordinate in metres.
   * @returns {string} The coordinate with at most two decimals.
   */
  static metres(value) {
    return String(Math.round(value * 100) / 100);
  }

  /**
   * Remove every listener.
   */
  dispose() {
    this.#shown.dispose();
  }
}
