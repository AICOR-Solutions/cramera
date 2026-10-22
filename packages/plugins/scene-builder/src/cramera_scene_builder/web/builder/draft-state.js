/**
 * The draft being edited and its history: every edit is checked, kept as one step, and
 * can be undone and redone.
 */

import {
  AppearanceKey,
  DraftKey,
  InstanceKey,
  LinkOffsetKey,
  NoticeKey,
  PROTOCOL_VERSION,
  ResourceKey,
  ResourceKind,
} from '../../../protocol.js';
import { InvalidDraft } from './draft-check.js';

/**
 * How many steps can be undone.
 */
export const HISTORY_LIMIT = 100;

/**
 * How far a duplicate stands from its original along x, in metres.
 */
export const DUPLICATE_OFFSET = 0.25;

/**
 * The name of a new draft.
 */
export const UNTITLED_DRAFT = 'Untitled scene';

/**
 * Starts the identities of instances the builder adds.
 */
const INSTANCE_PREFIX = 'instance-';

/**
 * Ends the name of a duplicate.
 */
const DUPLICATE_SUFFIX = ' copy';

/**
 * The indentation of an exported draft.
 */
const EXPORT_INDENTATION = 2;

// %% errors

/**
 * An edit of an instance the draft does not hold.
 */
export class UnknownInstance extends Error {
  /**
   * @param {string|null} identifier The identity that was given.
   */
  constructor(identifier) {
    super(`The draft holds no instance ${identifier}; select one first.`);
    /**
     * The identity that was given.
     * @type {string|null}
     */
    this.identifier = identifier;
  }
}

/**
 * A placement change of a locked reference point cloud.
 */
export class LockedReference extends Error {
  /**
   * @param {string} identifier The reference's identity.
   */
  constructor(identifier) {
    super(`Unlock ${identifier} to change its placement or scale.`);
    /**
     * The reference's identity.
     * @type {string}
     */
    this.identifier = identifier;
  }
}

/**
 * An instance of a resource the catalog does not offer.
 */
export class UnknownResource extends Error {
  /**
   * @param {string} identifier The resource identifier.
   */
  constructor(identifier) {
    super(`The catalog offers no resource ${identifier}.`);
    /**
     * The resource identifier.
     * @type {string}
     */
    this.identifier = identifier;
  }
}

// %% state

/**
 * @param {*} value A JSON value.
 * @returns {*} A copy sharing nothing with the value.
 */
function copyOf(value) {
  return structuredClone(value);
}

export class DraftState {
  /**
   * Checks every draft before it becomes current.
   * @type {import('./draft-check.js').DraftCheck}
   */
  #check;

  /**
   * The catalog's resources by identifier.
   * @type {Map<string, Object>}
   */
  #resources = new Map();

  /**
   * The current draft.
   * @type {Object}
   */
  #current;

  /**
   * The drafts before the current one, oldest first.
   * @type {Array<Object>}
   */
  #previous = [];

  /**
   * The drafts undone, most recently undone last.
   * @type {Array<Object>}
   */
  #following = [];

  /**
   * Called with the draft after every change.
   * @type {Set<function(Object): void>}
   */
  #listeners = new Set();

  /**
   * @param {import('./draft-check.js').DraftCheck} check Checks every draft.
   * @param {Object=} draft The draft to start from; an empty one by default.
   */
  constructor(check, draft = DraftState.empty()) {
    this.#check = check;
    this.#current = check.draft(draft);
  }

  /**
   * @param {string=} name The scene's name.
   * @returns {Object} A draft without instances.
   */
  static empty(name = UNTITLED_DRAFT) {
    return { [DraftKey.FORMAT_VERSION]: PROTOCOL_VERSION, [DraftKey.NAME]: name, [DraftKey.INSTANCES]: [] };
  }

  /**
   * @param {Array<Object>} resources The catalog's resources.
   */
  setResources(resources) {
    this.#resources = new Map(resources.map((resource) => [resource[ResourceKey.IDENTIFIER], resource]));
  }

  /**
   * @param {string} identifier A resource identifier.
   * @returns {Object|undefined} The catalog's resource.
   */
  resource(identifier) {
    return this.#resources.get(identifier);
  }

  /**
   * @returns {Object} A copy of the current draft.
   */
  get draft() {
    return copyOf(this.#current);
  }

  /**
   * @returns {boolean} Whether a step can be undone.
   */
  get canUndo() {
    return this.#previous.length > 0;
  }

  /**
   * @returns {boolean} Whether an undone step can be redone.
   */
  get canRedo() {
    return this.#following.length > 0;
  }

  /**
   * @param {string|null} identifier An instance identity.
   * @returns {Object|null} A copy of the instance, or null.
   */
  instance(identifier) {
    const instance = this.#current[DraftKey.INSTANCES].find((candidate) => candidate[InstanceKey.IDENTIFIER] === identifier);
    return instance ? copyOf(instance) : null;
  }

  /**
   * @param {function(Object): void} listener Called with the draft after every change.
   * @returns {function(): void} Removes the listener again.
   */
  subscribe(listener) {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  }

  /**
   * Make a draft current as one step.
   * @param {Object} draft The new draft.
   * @throws {InvalidDraft} When the draft is malformed or beyond a limit.
   */
  replace(draft) {
    const checked = this.#check.draft(draft);
    if (JSON.stringify(checked) === JSON.stringify(this.#current)) return;
    this.#previous.push(this.#current);
    if (this.#previous.length > HISTORY_LIMIT) this.#previous.shift();
    this.#current = checked;
    this.#following = [];
    this.#notify();
  }

  /**
   * Start over with a draft whose history is empty.
   * @param {Object} draft The draft.
   * @throws {InvalidDraft} When the draft is malformed or beyond a limit.
   */
  reset(draft) {
    this.#current = this.#check.draft(draft);
    this.#previous = [];
    this.#following = [];
    this.#notify();
  }

  /**
   * Place a copy of a resource at the origin.
   * @param {string} identifier The resource identifier.
   * @param {{name: (string|undefined), scale: (Array<number>|undefined)}=} options The
   *   instance's name and scale; the resource's name and its own size by default.
   * @returns {Object} The new instance.
   * @throws {UnknownResource} When the catalog does not offer the resource.
   */
  add(identifier, options = {}) {
    const resource = this.#resources.get(identifier);
    if (!resource) throw new UnknownResource(identifier);
    const instance = {
      [InstanceKey.IDENTIFIER]: this.#nextIdentity(),
      [InstanceKey.ASSET]: identifier,
      [InstanceKey.NAME]: options.name ?? resource[ResourceKey.NAME],
      [InstanceKey.POSITION]: [0, 0, 0],
      [InstanceKey.ROTATION]: [0, 0, 0],
      [InstanceKey.SCALE]: options.scale ?? [1, 1, 1],
    };
    if (resource[ResourceKey.KIND] === ResourceKind.POINT_CLOUD) instance[InstanceKey.POINT_CLOUD] = this.#check.defaultAppearance;
    const draft = this.draft;
    draft[DraftKey.INSTANCES].push(instance);
    draft[DraftKey.NOTICES] = this.#notices(draft, resource);
    this.replace(draft);
    return this.instance(instance[InstanceKey.IDENTIFIER]);
  }

  /**
   * @param {string} identifier An instance identity.
   * @returns {Object} The copy, beside the original.
   */
  duplicate(identifier) {
    const copy = this.#required(identifier);
    copy[InstanceKey.IDENTIFIER] = this.#nextIdentity();
    copy[InstanceKey.NAME] = `${copy[InstanceKey.NAME]}${DUPLICATE_SUFFIX}`;
    copy[InstanceKey.POSITION][0] += DUPLICATE_OFFSET;
    const draft = this.draft;
    draft[DraftKey.INSTANCES].push(copy);
    this.replace(draft);
    return this.instance(copy[InstanceKey.IDENTIFIER]);
  }

  /**
   * @param {string} identifier An instance identity.
   */
  remove(identifier) {
    const draft = this.draft;
    draft[DraftKey.INSTANCES] = draft[DraftKey.INSTANCES].filter((instance) => instance[InstanceKey.IDENTIFIER] !== identifier);
    this.replace(draft);
  }

  /**
   * @param {string} name The scene's new name.
   */
  rename(name) {
    this.replace({ ...this.draft, [DraftKey.NAME]: name });
  }

  /**
   * @param {string} identifier An instance identity.
   * @param {string} name The instance's new name.
   */
  renameInstance(identifier, name) {
    this.#edit(identifier, (instance) => {
      instance[InstanceKey.NAME] = name;
    });
  }

  /**
   * Move a whole instance or one of its links.
   * @param {string} identifier An instance identity.
   * @param {{position: Array<number>, rotation: Array<number>}} pose The new position
   *   and roll, pitch and yaw; for a link, its offset in its parent's frame.
   * @param {string|null=} link The moved link, or null for the whole instance.
   * @throws {LockedReference} For a locked reference point cloud.
   */
  place(identifier, pose, link = null) {
    this.#edit(identifier, (instance) => {
      this.#requireUnlocked(instance);
      const placement = { [LinkOffsetKey.POSITION]: pose.position, [LinkOffsetKey.ROTATION]: pose.rotation };
      if (link === null) Object.assign(instance, placement);
      else instance[InstanceKey.LINK_OFFSETS][link] = placement;
    });
  }

  /**
   * @param {string} identifier An instance identity.
   * @param {Array<number>} scale The factor along each axis.
   * @throws {LockedReference} For a locked reference point cloud.
   */
  setScale(identifier, scale) {
    this.#edit(identifier, (instance) => {
      this.#requireUnlocked(instance);
      instance[InstanceKey.SCALE] = scale;
    });
  }

  /**
   * @param {string} identifier The identity of a reference point cloud.
   * @param {Object} changes The appearance fields to change, by `AppearanceKey`.
   * @throws {InvalidDraft} When the instance is no point cloud.
   */
  setAppearance(identifier, changes) {
    this.#edit(identifier, (instance) => {
      if (!instance[InstanceKey.POINT_CLOUD]) throw new InvalidDraft(InstanceKey.POINT_CLOUD, `${identifier} is no point cloud`);
      instance[InstanceKey.POINT_CLOUD] = { ...instance[InstanceKey.POINT_CLOUD], ...changes };
    });
  }

  /**
   * Restore a link's authored placement.
   * @param {string} identifier An instance identity.
   * @param {string} link The link's name.
   */
  resetLink(identifier, link) {
    this.#edit(identifier, (instance) => {
      delete instance[InstanceKey.LINK_OFFSETS][link];
    });
  }

  /**
   * @param {string} identifier An instance identity.
   * @param {string} joint The joint's name.
   * @param {number} value The joint's value in radians or metres.
   */
  setJoint(identifier, joint, value) {
    this.#edit(identifier, (instance) => {
      instance[InstanceKey.JOINT_POSITIONS][joint] = value;
    });
  }

  /**
   * @returns {boolean} Whether a step was undone.
   */
  undo() {
    if (!this.canUndo) return false;
    this.#following.push(this.#current);
    this.#current = this.#previous.pop();
    this.#notify();
    return true;
  }

  /**
   * @returns {boolean} Whether an undone step was redone.
   */
  redo() {
    if (!this.canRedo) return false;
    this.#previous.push(this.#current);
    this.#current = this.#following.pop();
    this.#notify();
    return true;
  }

  /**
   * @returns {string} The draft as the JSON file an export writes.
   */
  exportText() {
    return `${JSON.stringify(this.#current, null, EXPORT_INDENTATION)}\n`;
  }

  /**
   * @param {string} identifier An instance identity.
   * @param {function(Object): void} change Changes a copy of the instance.
   */
  #edit(identifier, change) {
    const draft = this.draft;
    const instance = draft[DraftKey.INSTANCES].find((candidate) => candidate[InstanceKey.IDENTIFIER] === identifier);
    if (!instance) throw new UnknownInstance(identifier);
    change(instance);
    this.replace(draft);
  }

  /**
   * @param {string} identifier An instance identity.
   * @returns {Object} A copy of the instance.
   * @throws {UnknownInstance} When the draft holds no such instance.
   */
  #required(identifier) {
    const instance = this.instance(identifier);
    if (!instance) throw new UnknownInstance(identifier);
    return instance;
  }

  /**
   * @param {Object} instance An instance.
   * @throws {LockedReference} When it is a locked reference point cloud.
   */
  #requireUnlocked(instance) {
    if (instance[InstanceKey.POINT_CLOUD]?.[AppearanceKey.LOCKED]) throw new LockedReference(instance[InstanceKey.IDENTIFIER]);
  }

  /**
   * @returns {string} The first `instance-<n>` no instance of the draft has.
   */
  #nextIdentity() {
    const taken = new Set(this.#current[DraftKey.INSTANCES].map((instance) => instance[InstanceKey.IDENTIFIER]));
    let number = taken.size + 1;
    while (taken.has(`${INSTANCE_PREFIX}${number}`)) number += 1;
    return `${INSTANCE_PREFIX}${number}`;
  }

  /**
   * @param {Object} draft A draft.
   * @param {Object} resource A resource placed in it.
   * @returns {Array<Object>} The draft's notices with the resource's added.
   */
  #notices(draft, resource) {
    const notices = new Map((draft[DraftKey.NOTICES] ?? []).map((notice) => [notice[NoticeKey.ASSET], notice]));
    for (const notice of resource[ResourceKey.NOTICES] ?? []) notices.set(notice[NoticeKey.ASSET], notice);
    return [...notices.values()];
  }

  /**
   * Call every listener with the current draft.
   */
  #notify() {
    for (const listener of [...this.#listeners]) listener(this.draft);
  }
}
