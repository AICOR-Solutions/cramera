/**
 * The inspector of the selected instance: its name, placement, scale, link offsets,
 * joint values, reference appearance and notices.
 */

import { AppearanceKey, InstanceKey, LinkOffsetKey, NoticeKey, ResourceKey, ResourceKind } from '../../../protocol.js';
import { BuilderAction, DomEvent, Elements } from './elements.js';
import { MISSING_RESOURCE } from './instance-list.js';
import { JointType } from './placed-instance.js';

/**
 * Degrees in a radian; the inspector shows angles in degrees.
 */
export const DEGREES_PER_RADIAN = 180 / Math.PI;

/**
 * Millimetres in a metre; the inspector shows point sizes in millimetres.
 */
export const MILLIMETRES_PER_METRE = 1000;

/**
 * How many decimals the inspector shows.
 */
const SHOWN_DECIMALS = 6;

/**
 * The scale steps the inspector offers, and resetting to the resource's size.
 */
const ScaleStep = Object.freeze({ HALF: 0.5, DOUBLE: 2 });

/**
 * How a notice opens: in a new window that cannot reach the builder.
 */
const NewWindow = Object.freeze({ TARGET: '_blank', RELATION: 'noopener' });

/**
 * The part selector's choice of the whole instance.
 */
const WHOLE_INSTANCE = '';

/**
 * The names of a vector's components, as the fields show them.
 */
const AXES = Object.freeze(['X', 'Y', 'Z']);

/**
 * The names of a rotation's components, as the fields show them.
 */
const ANGLES = Object.freeze(['Roll', 'Pitch', 'Yaw']);

// %% errors

/**
 * A field left empty or holding no number.
 */
export class MissingNumber extends Error {
  /**
   * @param {string} field The field's name.
   */
  constructor(field) {
    super(`Enter a number for ${field}.`);
    /**
     * The field's name.
     * @type {string}
     */
    this.field = field;
  }
}

// %% actions

/**
 * What the inspector asks of the page.
 */
export class InspectorActions {
  /**
   * @param {Object} callbacks The callbacks, by name: `rename(name)`, `duplicate()`,
   *   `remove()`, `chooseLink(link)`, `place(position, rotation)`, `scale(scale)`,
   *   `setProportional(proportional)`, `setAppearance(changes)`, `resetLink()`,
   *   `setJoint(joint, value)` and `noticeUrl(asset)`.
   */
  constructor(callbacks) {
    /**
     * Renames the instance.
     * @type {function(string): void}
     */
    this.rename = callbacks.rename;
    /**
     * Places a copy of the instance beside it.
     * @type {function(): void}
     */
    this.duplicate = callbacks.duplicate;
    /**
     * Removes the instance.
     * @type {function(): void}
     */
    this.remove = callbacks.remove;
    /**
     * Selects one of the instance's links, or null for the whole instance.
     * @type {function(string|null): void}
     */
    this.chooseLink = callbacks.chooseLink;
    /**
     * Places the instance or its selected link, with a rotation in radians.
     * @type {function(Array<number>, Array<number>): void}
     */
    this.place = callbacks.place;
    /**
     * Scales the instance.
     * @type {function(Array<number>): void}
     */
    this.scale = callbacks.scale;
    /**
     * Sets whether scaling one axis scales all three alike.
     * @type {function(boolean): void}
     */
    this.setProportional = callbacks.setProportional;
    /**
     * Changes how a reference point cloud is shown.
     * @type {function(Object): void}
     */
    this.setAppearance = callbacks.setAppearance;
    /**
     * Restores the selected link's authored placement.
     * @type {function(): void}
     */
    this.resetLink = callbacks.resetLink;
    /**
     * Sets a joint's value.
     * @type {function(string, number): void}
     */
    this.setJoint = callbacks.setJoint;
    /**
     * The URL of a notice file.
     * @type {function(string): string}
     */
    this.noticeUrl = callbacks.noticeUrl;
  }
}

// %% inspector

export class InspectorView {
  /**
   * Builds the fixed fields and owns their listeners.
   * @type {Elements}
   */
  #elements;

  /**
   * Builds the joint fields and notices of the shown instance, replaced on every showing.
   * @type {Elements}
   */
  #parts;

  /**
   * What the inspector asks of the page.
   * @type {InspectorActions}
   */
  #actions;

  /**
   * The shown instance, or null.
   * @type {Object|null}
   */
  #instance = null;

  /**
   * Whether scaling one axis scales all three alike.
   * @type {boolean}
   */
  #proportional = true;

  /**
   * The fields of the inspector.
   * @type {Object<string, HTMLElement>}
   */
  #fields = {};

  /**
   * The inspector's element.
   * @type {HTMLElement}
   */
  element;

  /**
   * @param {Elements} elements Builds the fields.
   * @param {InspectorActions} actions What the inspector asks of the page.
   */
  constructor(elements, actions) {
    this.#elements = elements;
    this.#parts = new Elements(elements.document);
    this.#actions = actions;
    this.element = elements.create('section', 'builder-section inspector');
    const fields = this.#fields;
    fields.empty = elements.create('p', 'muted', 'Select an instance to arrange it.');
    fields.editor = elements.create('div', 'inspector-editor');
    fields.kind = elements.create('span', 'badge');
    const heading = elements.create('div', 'section-heading');
    heading.append(elements.create('h2', '', 'Selected instance'), fields.kind);
    fields.name = elements.input('text', BuilderAction.RENAME, () => actions.rename(fields.name.value.trim()));
    const buttons = elements.create('div', 'button-row');
    buttons.append(elements.button('Duplicate', BuilderAction.DUPLICATE, () => actions.duplicate()), elements.button('Remove', BuilderAction.REMOVE, () => actions.remove()));
    fields.reference = this.#referenceFields();
    fields.link = elements.select(BuilderAction.CHOOSE_LINK, () => actions.chooseLink(fields.link.value === WHOLE_INSTANCE ? null : fields.link.value));
    fields.position = this.#vector('Position · m', AXES, BuilderAction.POSITION, () => this.#place());
    fields.rotation = this.#vector('Rotation · °', ANGLES, BuilderAction.ROTATION, () => this.#place());
    fields.scaling = this.#scaleFields();
    fields.resetLink = elements.button('Restore the authored placement', BuilderAction.RESET_LINK, () => actions.resetLink());
    fields.joints = elements.create('div', 'joint-fields');
    fields.notices = elements.create('div', 'notice-list');
    fields.editor.append(
      elements.label('Name', fields.name),
      buttons,
      fields.reference,
      elements.label('Part', fields.link),
      fields.position.element,
      fields.rotation.element,
      fields.scaling,
      fields.resetLink,
      fields.joints,
      fields.notices,
    );
    this.element.append(heading, fields.empty, fields.editor);
    this.show(null, undefined, { links: [], joints: [] }, null);
  }

  /**
   * @param {Object|null} instance The selected instance, or null.
   * @param {Object|undefined} resource Its catalog resource.
   * @param {{links: Array<string>, joints: Array<Object>}} structure Its model's links and
   *   movable joints.
   * @param {string|null} link The selected link, or null for the whole instance.
   */
  show(instance, resource, structure, link) {
    this.#instance = instance;
    this.#parts.dispose();
    const fields = this.#fields;
    fields.empty.hidden = instance !== null;
    fields.editor.hidden = instance === null;
    fields.kind.hidden = instance === null;
    if (instance === null) return;
    const locked = Boolean(instance[InstanceKey.POINT_CLOUD]?.[AppearanceKey.LOCKED]);
    fields.kind.textContent = resource?.[ResourceKey.CATEGORY] ?? MISSING_RESOURCE;
    fields.name.value = instance[InstanceKey.NAME];
    this.#showReference(instance[InstanceKey.POINT_CLOUD]);
    const links = [...new Set([...structure.links, ...Object.keys(instance[InstanceKey.LINK_OFFSETS])])];
    this.#elements.options(
      fields.link,
      [{ value: WHOLE_INSTANCE, label: 'Whole instance' }, ...links.map((name) => ({ value: name, label: name }))],
      link ?? WHOLE_INSTANCE,
    );
    fields.link.disabled = resource?.[ResourceKey.KIND] !== ResourceKind.URDF;
    const pose = link === null ? instance : (instance[InstanceKey.LINK_OFFSETS][link] ?? { [LinkOffsetKey.POSITION]: [0, 0, 0], [LinkOffsetKey.ROTATION]: [0, 0, 0] });
    fields.position.write(pose[InstanceKey.POSITION]);
    fields.rotation.write(pose[InstanceKey.ROTATION].map((angle) => angle * DEGREES_PER_RADIAN));
    fields.scale.write(instance[InstanceKey.SCALE]);
    fields.scaling.hidden = link !== null;
    fields.resetLink.hidden = link === null;
    for (const input of [...fields.position.inputs, ...fields.rotation.inputs, ...fields.scale.inputs]) input.disabled = locked;
    this.#showJoints(instance, structure.joints);
    this.#showNotices(resource);
  }

  /**
   * Remove every listener of the inspector.
   */
  dispose() {
    this.#parts.dispose();
  }

  /**
   * @param {string} legend The group's legend.
   * @param {Array<string>} names The components' names.
   * @param {string} action The fields' `BuilderAction` value.
   * @param {function(): void} onChange Called when a component changes.
   * @returns {{element: HTMLElement, inputs: Array<HTMLInputElement>, read: function(): Array<number>, write: function(Array<number>): void}}
   *   The group of three number fields.
   */
  #vector(legend, names, action, onChange) {
    const element = this.#elements.create('fieldset', 'vector-fields');
    element.append(this.#elements.create('legend', '', legend));
    const inputs = names.map((name) => {
      const input = this.#elements.input('number', action, onChange);
      input.dataset.component = name;
      element.append(this.#elements.label(name, input));
      return input;
    });
    return {
      element,
      inputs,
      read: () => inputs.map((input, index) => this.#number(input, `${legend} ${names[index]}`)),
      write: (values) => inputs.forEach((input, index) => {
        input.value = String(Number(values[index].toFixed(SHOWN_DECIMALS)));
      }),
    };
  }

  /**
   * @returns {HTMLElement} The scale fields, the proportional switch and the scale steps.
   */
  #scaleFields() {
    const elements = this.#elements;
    this.#fields.scale = this.#vector('Scale · factor', AXES, BuilderAction.SCALE, () => {});
    this.#fields.scale.inputs.forEach((input, index) => elements.listen(input, DomEvent.CHANGE, () => this.#changeScale(index)));
    const proportional = elements.input('checkbox', BuilderAction.PROPORTIONAL, () => {
      this.#proportional = proportional.checked;
      this.#actions.setProportional(this.#proportional);
    });
    proportional.checked = this.#proportional;
    const steps = elements.create('div', 'button-row');
    steps.append(
      elements.button('× 0.5', BuilderAction.SCALE, () => this.#scaleBy(ScaleStep.HALF)),
      elements.button('× 2', BuilderAction.SCALE, () => this.#scaleBy(ScaleStep.DOUBLE)),
      elements.button('Reset scale', BuilderAction.SCALE, () => this.#actions.scale([1, 1, 1])),
    );
    const group = elements.create('div', 'scale-fields');
    group.append(this.#fields.scale.element, elements.label('Keep proportions', proportional, 'switch'), steps);
    return group;
  }

  /**
   * @returns {HTMLElement} The fields of a reference point cloud's appearance.
   */
  #referenceFields() {
    const elements = this.#elements;
    const fields = this.#fields;
    const section = elements.create('fieldset', 'reference-fields');
    section.append(elements.create('legend', '', 'Point cloud reference'));
    fields.visible = elements.input('checkbox', BuilderAction.VISIBLE, () => this.#actions.setAppearance({ [AppearanceKey.VISIBLE]: fields.visible.checked }));
    fields.locked = elements.input('checkbox', BuilderAction.LOCKED, () => this.#actions.setAppearance({ [AppearanceKey.LOCKED]: fields.locked.checked }));
    fields.opacity = elements.input('number', BuilderAction.OPACITY, () => this.#actions.setAppearance({ [AppearanceKey.OPACITY]: this.#number(fields.opacity, 'opacity') }));
    fields.pointSize = elements.input('number', BuilderAction.POINT_SIZE, () =>
      this.#actions.setAppearance({ [AppearanceKey.POINT_SIZE]: this.#number(fields.pointSize, 'point size') / MILLIMETRES_PER_METRE }),
    );
    section.append(
      elements.label('Show the reference', fields.visible, 'switch'),
      elements.label('Lock its placement', fields.locked, 'switch'),
      elements.label('Opacity', fields.opacity),
      elements.label('Point size · mm', fields.pointSize),
    );
    return section;
  }

  /**
   * @param {Object|undefined} appearance How the reference is shown, or undefined for a model.
   */
  #showReference(appearance) {
    const fields = this.#fields;
    fields.reference.hidden = !appearance;
    if (!appearance) return;
    fields.visible.checked = appearance[AppearanceKey.VISIBLE];
    fields.locked.checked = appearance[AppearanceKey.LOCKED];
    fields.opacity.value = String(appearance[AppearanceKey.OPACITY]);
    fields.pointSize.value = String(Number((appearance[AppearanceKey.POINT_SIZE] * MILLIMETRES_PER_METRE).toFixed(SHOWN_DECIMALS)));
  }

  /**
   * @param {Object} instance The shown instance.
   * @param {Array<Object>} joints Its model's movable joints.
   */
  #showJoints(instance, joints) {
    const rows = joints.map((joint) => {
      const angular = joint.type !== JointType.PRISMATIC;
      const factor = angular ? DEGREES_PER_RADIAN : 1;
      const input = this.#parts.input('number', BuilderAction.JOINT, () => this.#actions.setJoint(joint.name, this.#number(input, joint.name) / factor));
      input.dataset.joint = joint.name;
      input.value = String(Number(((instance[InstanceKey.JOINT_POSITIONS][joint.name] ?? 0) * factor).toFixed(SHOWN_DECIMALS)));
      if (joint.type !== JointType.CONTINUOUS && Number.isFinite(joint.lower)) input.min = String(joint.lower * factor);
      if (joint.type !== JointType.CONTINUOUS && Number.isFinite(joint.upper)) input.max = String(joint.upper * factor);
      return this.#parts.label(`${joint.name} · ${angular ? '°' : 'm'}`, input);
    });
    this.#fields.joints.replaceChildren(...(rows.length ? [this.#parts.create('h3', '', 'Joints'), ...rows] : []));
  }

  /**
   * @param {Object|undefined} resource The shown instance's resource.
   */
  #showNotices(resource) {
    const notices = resource?.[ResourceKey.NOTICES] ?? [];
    const links = notices.map((notice) => {
      const link = this.#parts.create('a', '', notice[NoticeKey.NAME]);
      link.href = this.#actions.noticeUrl(notice[NoticeKey.ASSET]);
      link.target = NewWindow.TARGET;
      link.rel = NewWindow.RELATION;
      link.title = notice[NoticeKey.ASSET];
      return link;
    });
    const source = this.#parts.create('p', 'muted', resource?.[ResourceKey.IDENTIFIER] ?? this.#instance[InstanceKey.ASSET]);
    this.#fields.notices.replaceChildren(this.#parts.create('h3', '', 'Source and notices'), source, ...links);
  }

  /**
   * Place the instance or link as the position and rotation fields say.
   */
  #place() {
    const rotation = this.#fields.rotation.read().map((angle) => angle / DEGREES_PER_RADIAN);
    this.#actions.place(this.#fields.position.read(), rotation);
  }

  /**
   * @param {number} index The axis whose field changed.
   */
  #changeScale(index) {
    const requested = this.#fields.scale.read();
    const current = this.#instance[InstanceKey.SCALE];
    const ratio = requested[index] / current[index];
    this.#actions.scale(this.#proportional ? current.map((factor) => factor * ratio) : requested);
  }

  /**
   * @param {number} factor The factor every axis is multiplied by.
   */
  #scaleBy(factor) {
    this.#actions.scale(this.#instance[InstanceKey.SCALE].map((value) => value * factor));
  }

  /**
   * @param {HTMLInputElement} input A number field.
   * @param {string} field The field's name.
   * @returns {number} Its number.
   * @throws {MissingNumber} When it is empty or holds no number.
   */
  #number(input, field) {
    const value = Number(input.value);
    if (!String(input.value).trim() || !Number.isFinite(value)) throw new MissingNumber(field);
    return value;
  }
}
