/**
 * The plan's free objects: adding copies of object models, where each starts, and
 * removing them.
 */

import { ObjectModelKey, PlanBuilderCatalogKey, PlannedObjectKey } from '../../../protocol.js';
import { Elements, PlanAction } from './elements.js';
import { PlanPose } from './poses.js';

// %% view

export class ObjectsView {
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
   * The object model added next.
   * @type {string|null}
   */
  #model = null;

  /**
   * @param {Document} document The page's document.
   * @param {Object} editor The page: `state` (the `PlanState`), `edit(change)` and
   *   `select(selection)`.
   */
  constructor(document, editor) {
    this.#editor = editor;
    this.#shown = new Elements(document);
    this.element = this.#shown.create('div', 'objects');
  }

  /**
   * Show the objects.
   * @param {string|null} selected The identity of the selected object, or null.
   */
  render(selected = null) {
    const document = this.#shown.document;
    this.#shown.dispose();
    const elements = (this.#shown = new Elements(document));
    const state = this.#editor.state;
    const models = state.catalog[PlanBuilderCatalogKey.OBJECTS].map((model) => ({ value: model[ObjectModelKey.IDENTIFIER], label: model[ObjectModelKey.NAME] }));
    if (models.length === 0) {
      this.element.replaceChildren(elements.create('p', 'empty', 'The CRAM workspace offers no object models here.'));
      return;
    }
    const model = elements.select(PlanAction.OBJECT_MODEL, models, this.#model ?? models[0].value, (value) => {
      this.#model = value;
    });
    const adding = elements.create('div', 'button-row');
    adding.append(model, elements.button('Add object', PlanAction.ADD_OBJECT, () => this.#editor.edit(() => state.addObject(model.value))));
    const list = elements.create('ul', 'object-list');
    list.append(...state.objects().map((item) => this.#entry(item, selected)));
    this.element.replaceChildren(adding, list);
  }

  /**
   * @param {Object} item An object of the plan.
   * @param {string|null} selected The identity of the selected object, or null.
   * @returns {HTMLElement} The object's entry: its name, start position and heading.
   */
  #entry(item, selected) {
    const elements = this.#shown;
    const state = this.#editor.state;
    const identifier = item[PlannedObjectKey.IDENTIFIER];
    const pose = item[PlannedObjectKey.POSE];
    const position = PlanPose.position(pose);
    const entry = elements.create('li', identifier === selected ? 'object selected' : 'object');
    entry.dataset.object = identifier;
    const head = elements.create('div', 'object-head');
    head.append(
      elements.button(identifier, PlanAction.SELECT_OBJECT, () => this.#editor.select({ object: identifier })),
      elements.button('×', PlanAction.REMOVE_OBJECT, () => this.#editor.edit(() => state.removeObject(identifier))),
    );
    const row = elements.create('div', 'pose-row');
    row.append(
      ...['x', 'y', 'z'].map((axis, index) =>
        elements.number(axis, position[index], PlanAction.POSE, (value) => {
          const moved = [...position];
          moved[index] = value;
          this.#editor.edit(() => state.setObjectPose(identifier, PlanPose.moved(pose, moved)));
        }),
      ),
      elements.number('yaw°', PlanPose.degrees(PlanPose.yaw(pose)), PlanAction.POSE, (value) =>
        this.#editor.edit(() => state.setObjectPose(identifier, PlanPose.turned(pose, PlanPose.radians(value)))),
      ),
    );
    entry.append(head, row);
    return entry;
  }

  /**
   * Remove every listener.
   */
  dispose() {
    this.#shown.dispose();
  }
}
