/**
 * Checking scene drafts in the browser against the limits the server enforces, so an
 * edit or an imported file is refused before it reaches the history.
 */

import {
  AppearanceKey,
  DraftKey,
  InstanceKey,
  LimitsKey,
  LinkOffsetKey,
  NoticeKey,
  PROTOCOL_VERSION,
} from '../../../protocol.js';

/**
 * The characters an instance identity is made of.
 */
const IDENTITY_CHARACTERS = /^[A-Za-z0-9_-]+$/;

/**
 * Control characters, which names and references must not hold.
 */
const CONTROL_CHARACTERS = /[\u0000-\u001f]/;

/**
 * Keys that would change an object's prototype instead of naming a link or joint.
 */
const PROTOTYPE_KEYS = Object.freeze(['__proto__', 'prototype', 'constructor']);

/**
 * Separates the major and minor number of a protocol version.
 */
const VERSION_SEPARATOR = '.';

/**
 * The number of components of a position, rotation or scale.
 */
export const VECTOR_LENGTH = 3;

/**
 * The scale of an instance shown at the size of its resource.
 */
export const UNIT_SCALE = Object.freeze([1, 1, 1]);

// %% errors

/**
 * A draft, or a change to one, that the builder refuses.
 */
export class InvalidDraft extends Error {
  /**
   * @param {string} location Where the refused value sits, such as `instances.cup.position`.
   * @param {string} reason Why it is refused.
   */
  constructor(location, reason) {
    super(`${location}: ${reason}`);
    /**
     * Where the refused value sits.
     * @type {string}
     */
    this.location = location;
    /**
     * Why it is refused.
     * @type {string}
     */
    this.reason = reason;
  }
}

// %% check

export class DraftCheck {
  /**
   * The limits, by `LimitsKey`.
   * @type {Object}
   */
  #limits;

  /**
   * How a reference placed without an appearance is shown, by `AppearanceKey`.
   * @type {Object}
   */
  #defaultAppearance;

  /**
   * @param {Object} limits The catalog's limits, by `LimitsKey`.
   * @param {Object} defaultAppearance The catalog's default appearance, by `AppearanceKey`.
   */
  constructor(limits, defaultAppearance) {
    this.#limits = limits;
    this.#defaultAppearance = defaultAppearance;
  }

  /**
   * @returns {Object} How a newly placed reference point cloud is shown.
   */
  get defaultAppearance() {
    return { ...this.#defaultAppearance };
  }

  /**
   * @param {*} document A draft as a person or file gave it.
   * @returns {Object} The draft with every left-out field at its default.
   * @throws {InvalidDraft} When the draft is malformed or beyond a limit.
   */
  draft(document) {
    this.#object(document, DraftKey, 'draft');
    this.#version(document[DraftKey.FORMAT_VERSION]);
    const instances = document[DraftKey.INSTANCES] ?? [];
    this.#count(DraftKey.INSTANCES, instances, Array.isArray(instances));
    const identities = new Set();
    const checked = instances.map((instance) => {
      const result = this.instance(instance);
      if (identities.has(result[InstanceKey.IDENTIFIER])) throw new InvalidDraft(DraftKey.INSTANCES, `two instances are named ${result[InstanceKey.IDENTIFIER]}`);
      identities.add(result[InstanceKey.IDENTIFIER]);
      return result;
    });
    const notices = document[DraftKey.NOTICES] ?? [];
    this.#count(DraftKey.NOTICES, notices, Array.isArray(notices));
    const result = {
      [DraftKey.FORMAT_VERSION]: PROTOCOL_VERSION,
      [DraftKey.NAME]: this.#text(DraftKey.NAME, document[DraftKey.NAME], this.#limits[LimitsKey.MAXIMUM_NAME_LENGTH]),
      [DraftKey.INSTANCES]: checked,
      [DraftKey.NOTICES]: notices.map((notice) => this.#notice(notice)),
    };
    if (document[DraftKey.SOURCE_SCENE] !== undefined && document[DraftKey.SOURCE_SCENE] !== null) {
      result[DraftKey.SOURCE_SCENE] = this.#text(DraftKey.SOURCE_SCENE, document[DraftKey.SOURCE_SCENE], this.#limits[LimitsKey.MAXIMUM_REFERENCE_LENGTH]);
    }
    const size = new TextEncoder().encode(JSON.stringify(result)).length;
    if (size > this.#limits[LimitsKey.MAXIMUM_DOCUMENT_BYTES]) throw new InvalidDraft(DraftKey.NAME, `the draft has ${size} bytes; at most ${this.#limits[LimitsKey.MAXIMUM_DOCUMENT_BYTES]} are kept`);
    return result;
  }

  /**
   * @param {*} instance One placed resource of a draft.
   * @returns {Object} The instance with every left-out field at its default.
   * @throws {InvalidDraft} When the instance is malformed or beyond a limit.
   */
  instance(instance) {
    this.#object(instance, InstanceKey, DraftKey.INSTANCES);
    const identifier = this.#identity(instance[InstanceKey.IDENTIFIER]);
    const location = `${DraftKey.INSTANCES}.${identifier}`;
    const offsets = instance[InstanceKey.LINK_OFFSETS] ?? {};
    const joints = instance[InstanceKey.JOINT_POSITIONS] ?? {};
    const result = {
      [InstanceKey.IDENTIFIER]: identifier,
      [InstanceKey.ASSET]: this.#text(`${location}.${InstanceKey.ASSET}`, instance[InstanceKey.ASSET], this.#limits[LimitsKey.MAXIMUM_REFERENCE_LENGTH]),
      [InstanceKey.NAME]: this.#text(`${location}.${InstanceKey.NAME}`, instance[InstanceKey.NAME], this.#limits[LimitsKey.MAXIMUM_NAME_LENGTH]),
      [InstanceKey.POSITION]: this.vector(`${location}.${InstanceKey.POSITION}`, instance[InstanceKey.POSITION]),
      [InstanceKey.ROTATION]: this.vector(`${location}.${InstanceKey.ROTATION}`, instance[InstanceKey.ROTATION]),
      [InstanceKey.SCALE]: this.scale(`${location}.${InstanceKey.SCALE}`, instance[InstanceKey.SCALE] ?? UNIT_SCALE),
      [InstanceKey.LINK_OFFSETS]: this.#mapping(`${location}.${InstanceKey.LINK_OFFSETS}`, offsets, (key, offset) => this.#offset(key, offset)),
      [InstanceKey.JOINT_POSITIONS]: this.#mapping(`${location}.${InstanceKey.JOINT_POSITIONS}`, joints, (key, value) => this.#number(key, value, this.#limits[LimitsKey.MAXIMUM_COORDINATE])),
    };
    const appearance = instance[InstanceKey.POINT_CLOUD];
    if (appearance !== undefined && appearance !== null) result[InstanceKey.POINT_CLOUD] = this.appearance(`${location}.${InstanceKey.POINT_CLOUD}`, appearance);
    return result;
  }

  /**
   * @param {string} location Where the vector sits.
   * @param {*} value A position or rotation.
   * @returns {Array<number>} A copy of the vector.
   * @throws {InvalidDraft} Unless it is three finite numbers within the coordinate limit.
   */
  vector(location, value) {
    if (!Array.isArray(value) || value.length !== VECTOR_LENGTH) throw new InvalidDraft(location, 'expected three numbers');
    return value.map((component) => this.#number(location, component, this.#limits[LimitsKey.MAXIMUM_COORDINATE]));
  }

  /**
   * @param {string} location Where the scale sits.
   * @param {*} value The factor along each axis.
   * @returns {Array<number>} A copy of the scale.
   * @throws {InvalidDraft} Unless every factor is positive and within the scale limit.
   */
  scale(location, value) {
    const scale = this.vector(location, value);
    if (scale.some((factor) => factor <= 0 || factor > this.#limits[LimitsKey.MAXIMUM_SCALE])) {
      throw new InvalidDraft(location, `scale factors are positive and at most ${this.#limits[LimitsKey.MAXIMUM_SCALE]}`);
    }
    return scale;
  }

  /**
   * @param {string} location Where the appearance sits.
   * @param {*} value How a reference point cloud is shown.
   * @returns {Object} The appearance with left-out fields at the catalog's default.
   * @throws {InvalidDraft} When a field is of the wrong type or beyond its limit.
   */
  appearance(location, value) {
    this.#object(value, AppearanceKey, location);
    const result = { ...this.#defaultAppearance, ...value };
    for (const key of [AppearanceKey.VISIBLE, AppearanceKey.LOCKED]) {
      if (typeof result[key] !== 'boolean') throw new InvalidDraft(`${location}.${key}`, 'expected true or false');
    }
    this.#between(`${location}.${AppearanceKey.POINT_SIZE}`, result[AppearanceKey.POINT_SIZE], this.#limits[LimitsKey.MINIMUM_POINT_SIZE], this.#limits[LimitsKey.MAXIMUM_POINT_SIZE]);
    this.#between(`${location}.${AppearanceKey.OPACITY}`, result[AppearanceKey.OPACITY], this.#limits[LimitsKey.MINIMUM_OPACITY], this.#limits[LimitsKey.MAXIMUM_OPACITY]);
    return result;
  }

  /**
   * @param {*} version The draft's protocol version, or undefined for a draft without one.
   * @throws {InvalidDraft} When the draft was written with another major version.
   */
  #version(version) {
    if (version === undefined) return;
    const major = (text) => String(text).split(VERSION_SEPARATOR)[0];
    if (major(version) !== major(PROTOCOL_VERSION)) throw new InvalidDraft(DraftKey.FORMAT_VERSION, `version ${version} is not readable by version ${PROTOCOL_VERSION}`);
  }

  /**
   * @param {*} notice An attribution notice.
   * @returns {Object} A copy of the notice.
   */
  #notice(notice) {
    this.#object(notice, NoticeKey, DraftKey.NOTICES);
    return {
      [NoticeKey.NAME]: this.#text(`${DraftKey.NOTICES}.${NoticeKey.NAME}`, notice[NoticeKey.NAME], this.#limits[LimitsKey.MAXIMUM_NAME_LENGTH]),
      [NoticeKey.ASSET]: this.#text(`${DraftKey.NOTICES}.${NoticeKey.ASSET}`, notice[NoticeKey.ASSET], this.#limits[LimitsKey.MAXIMUM_REFERENCE_LENGTH]),
    };
  }

  /**
   * @param {string} location Where the offset sits.
   * @param {*} offset A link's offset.
   * @returns {Object} A copy of the offset.
   */
  #offset(location, offset) {
    this.#object(offset, LinkOffsetKey, location);
    return {
      [LinkOffsetKey.POSITION]: this.vector(`${location}.${LinkOffsetKey.POSITION}`, offset[LinkOffsetKey.POSITION]),
      [LinkOffsetKey.ROTATION]: this.vector(`${location}.${LinkOffsetKey.ROTATION}`, offset[LinkOffsetKey.ROTATION]),
    };
  }

  /**
   * @param {string} location Where the mapping sits.
   * @param {*} mapping Values by link or joint name.
   * @param {function(string, *): *} read Checks one value, given its location.
   * @returns {Object} A copy of the mapping.
   */
  #mapping(location, mapping, read) {
    this.#object(mapping, null, location);
    const entries = Object.entries(mapping);
    this.#count(location, entries, true);
    const result = {};
    for (const [key, value] of entries) {
      const entryLocation = `${location}.${key}`;
      this.#text(entryLocation, key, this.#limits[LimitsKey.MAXIMUM_REFERENCE_LENGTH]);
      if (PROTOTYPE_KEYS.includes(key)) throw new InvalidDraft(entryLocation, 'this name is reserved');
      result[key] = read(entryLocation, value);
    }
    return result;
  }

  /**
   * @param {*} value An object of a draft.
   * @param {Object|null} keys The keys the object may hold, or null for free keys.
   * @param {string} location Where the object sits.
   * @throws {InvalidDraft} When the value is no object or holds an unknown key.
   */
  #object(value, keys, location) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new InvalidDraft(location, 'expected an object');
    if (keys === null) return;
    const allowed = Object.values(keys);
    const unknown = Object.keys(value).find((key) => !allowed.includes(key));
    if (unknown !== undefined) throw new InvalidDraft(location, `unknown field ${unknown}`);
  }

  /**
   * @param {*} identifier An instance identity.
   * @returns {string} The identity.
   * @throws {InvalidDraft} Unless it is a bounded run of letters, digits, `_` and `-`.
   */
  #identity(identifier) {
    if (typeof identifier !== 'string' || identifier.length > this.#limits[LimitsKey.MAXIMUM_IDENTIFIER_LENGTH] || !IDENTITY_CHARACTERS.test(identifier)) {
      throw new InvalidDraft(`${DraftKey.INSTANCES}.${InstanceKey.IDENTIFIER}`, 'use letters, digits, _ and - only');
    }
    return identifier;
  }

  /**
   * @param {string} location Where the text sits.
   * @param {*} text A name or reference.
   * @param {number} maximum How many characters it may have.
   * @returns {string} The text.
   * @throws {InvalidDraft} When it is blank, too long or holds control characters.
   */
  #text(location, text, maximum) {
    if (typeof text !== 'string' || !text.trim() || text.length > maximum || CONTROL_CHARACTERS.test(text)) {
      throw new InvalidDraft(location, `expected text of 1 to ${maximum} characters without control characters`);
    }
    return text;
  }

  /**
   * @param {string} location Where the number sits.
   * @param {*} value A coordinate, angle or joint value.
   * @param {number} maximum Its largest magnitude.
   * @returns {number} The number.
   */
  #number(location, value, maximum) {
    return this.#between(location, value, -maximum, maximum);
  }

  /**
   * @param {string} location Where the number sits.
   * @param {*} value A number.
   * @param {number} minimum The smallest allowed value.
   * @param {number} maximum The largest allowed value.
   * @returns {number} The number.
   * @throws {InvalidDraft} Unless it is a finite number within the bounds.
   */
  #between(location, value, minimum, maximum) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < minimum || value > maximum) {
      throw new InvalidDraft(location, `expected a number from ${minimum} to ${maximum}`);
    }
    return value;
  }

  /**
   * @param {string} location Where the entries sit.
   * @param {*} entries A list of a draft.
   * @param {boolean} isList Whether the value is a list.
   * @throws {InvalidDraft} When it is no list or holds more entries than a draft has instances.
   */
  #count(location, entries, isList) {
    if (!isList) throw new InvalidDraft(location, 'expected a list');
    if (entries.length > this.#limits[LimitsKey.MAXIMUM_INSTANCES]) throw new InvalidDraft(location, `at most ${this.#limits[LimitsKey.MAXIMUM_INSTANCES]} entries fit`);
  }
}
