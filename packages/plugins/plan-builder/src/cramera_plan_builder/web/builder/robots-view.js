/**
 * The plan's robots: which one's plan is edited, adding and removing robots, and the
 * edited robot's model, name and start pose.
 */

import { PlanBuilderCatalogKey, PlannedRobotKey, RobotModelKey } from '../../../protocol.js';
import { Elements, PlanAction } from './elements.js';
import { PlanPose } from './poses.js';
import { StepCardClass } from './step-card.js';

// %% view

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
   * Show the robots and the edited robot's settings.
   */
  render() {
    const document = this.#shown.document;
    this.#shown.dispose();
    const elements = (this.#shown = new Elements(document));
    const state = this.#editor.state;
    const robot = state.activeRobot();
    const models = state.catalog[PlanBuilderCatalogKey.ROBOTS].map((model) => ({ value: model[RobotModelKey.NAME], label: model[RobotModelKey.NAME] }));
    if (!robot) {
      this.element.replaceChildren(elements.create('p', 'empty', 'The CRAM workspace offers no robot here.'));
      return;
    }
    const identifier = robot[PlannedRobotKey.IDENTIFIER];
    const robots = state.robots().map((entry) => ({ value: entry[PlannedRobotKey.IDENTIFIER], label: `${entry[PlannedRobotKey.LABEL]} · ${entry[PlannedRobotKey.MODEL]}` }));
    const chosen = elements.select(PlanAction.SELECT_ROBOT, robots, identifier, (value) => this.#editor.edit(() => state.selectRobot(value)));
    const addedModel = elements.select(PlanAction.ROBOT_MODEL, models, this.#addedModel ?? robot[PlannedRobotKey.MODEL], (value) => {
      this.#addedModel = value;
    });
    const adding = elements.create('div', 'button-row');
    adding.append(
      addedModel,
      elements.button('Add robot', PlanAction.ADD_ROBOT, () => this.#editor.edit(() => state.addRobot(addedModel.value))),
    );
    const remove = elements.button('Remove', PlanAction.REMOVE_ROBOT, () => this.#editor.edit(() => state.removeRobot(identifier)));
    remove.disabled = state.robots().length <= 1;
    const label = elements.input('text', PlanAction.ROBOT_LABEL, () => this.#editor.edit(() => state.setRobotLabel(identifier, label.value)));
    label.value = robot[PlannedRobotKey.LABEL];
    const model = elements.select(PlanAction.ROBOT_MODEL, models, robot[PlannedRobotKey.MODEL], (value) => this.#editor.edit(() => state.setRobotModel(identifier, value)));
    const pose = robot[PlannedRobotKey.POSE];
    const [x, y] = PlanPose.position(pose);
    const place = (position, yaw) => this.#editor.edit(() => state.setRobotPose(identifier, PlanPose.of(...position, yaw)));
    const row = elements.create('div', StepCardClass.POSE_ROW);
    row.append(
      elements.number('x', x, PlanAction.POSE, (value) => place([value, y, 0], PlanPose.yaw(pose))),
      elements.number('y', y, PlanAction.POSE, (value) => place([x, value, 0], PlanPose.yaw(pose))),
      elements.number('yaw°', PlanPose.degrees(PlanPose.yaw(pose)), PlanAction.POSE, (value) => place([x, y, 0], PlanPose.radians(value))),
    );
    const editing = elements.create('div', 'button-row');
    editing.append(chosen, remove);
    this.element.replaceChildren(
      elements.label('plan of', editing),
      elements.label('name', label),
      elements.label('model', model),
      elements.label('start', row),
      elements.label('another robot', adding),
    );
  }

  /**
   * Remove every listener.
   */
  dispose() {
    this.#shown.dispose();
  }
}
