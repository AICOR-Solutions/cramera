/**
 * What a recorded trajectory sets at each frame: joint values per model, the robot's
 * root pose, the root pose of each robot instance, and the pose of each free object.
 */

import { ModelKey, SceneKey, SegmentKey, TrajectoryKey } from '../protocol.js';

/**
 * Separates a model's prefix from a joint name in trajectory keys.
 */
const PREFIX_SEPARATOR = '/';

// %% errors

/**
 * A trajectory with several frames whose frame rate neither it nor its scene names.
 */
export class MissingFrameRate extends Error {
  /**
   * @param {number} frameCount How many frames the trajectory has.
   */
  constructor(frameCount) {
    super(`A trajectory of ${frameCount} frames needs a frame rate.`);
    /**
     * How many frames the trajectory has.
     * @type {number}
     */
    this.frameCount = frameCount;
  }
}

// %% joint addresses

/**
 * The model and URDF joint a trajectory key drives.
 */
export class JointAddress {
  /**
   * @param {string} model The model's name.
   * @param {string} joint The joint's name in the model's URDF.
   */
  constructor(model, joint) {
    /**
     * The model's name.
     * @type {string}
     */
    this.model = model;
    /**
     * The joint's name in the model's URDF.
     * @type {string}
     */
    this.joint = joint;
  }
}

// %% frames

export class TrajectoryFrames {
  /**
   * The trajectory document.
   * @type {Object}
   */
  #trajectory;

  /**
   * The model and joint each trajectory key drives.
   * @type {Map<string, JointAddress>}
   */
  #addresses;

  /**
   * How many frames make one second.
   * @type {number}
   */
  #framesPerSecond;

  /**
   * The scene's steps on the timeline.
   * @type {Array<Object>}
   */
  #segments;

  /**
   * @param {Object} scene The scene description.
   * @param {Object} trajectory The trajectory document.
   * @throws {MissingFrameRate} When several frames have no frame rate.
   */
  constructor(scene, trajectory) {
    this.#trajectory = trajectory;
    this.#addresses = addressesOf(scene[SceneKey.MODELS] ?? []);
    this.#segments = scene[SceneKey.SEGMENTS] ?? [];
    const rate =
      trajectory[TrajectoryKey.FRAMES_PER_SECOND] ??
      trajectory[TrajectoryKey.LEGACY_FRAMES_PER_SECOND] ??
      scene[SceneKey.FRAMES_PER_SECOND] ??
      scene[SceneKey.LEGACY_FRAMES_PER_SECOND];
    if (rate === undefined && this.frameCount > 1) throw new MissingFrameRate(this.frameCount);
    this.#framesPerSecond = rate ?? 1;
  }

  /**
   * @returns {number} How many frames the trajectory has.
   */
  get frameCount() {
    return (this.#trajectory[TrajectoryKey.FRAMES] ?? []).length;
  }

  /**
   * @returns {number} How many frames make one second.
   */
  get framesPerSecond() {
    return this.#framesPerSecond;
  }

  /**
   * @returns {Array<string>} The trajectory keys no model's movable joints claim.
   */
  unassignedKeys() {
    const keys = new Set((this.#trajectory[TrajectoryKey.FRAMES] ?? []).flatMap((frame) => Object.keys(frame)));
    return [...keys].filter((key) => !this.#addresses.has(key)).sort();
  }

  /**
   * @param {number} frame A frame.
   * @returns {Map<string, Map<string, number>>} The joint values of each model.
   */
  jointValues(frame) {
    return this.jointValuesOf(this.#trajectory[TrajectoryKey.FRAMES]?.[frame] ?? {});
  }

  /**
   * @param {Object<string, number>} recorded Joint values by trajectory key, as a
   *   trajectory frame or a live state holds them.
   * @returns {Map<string, Map<string, number>>} The joint values of each model.
   */
  jointValuesOf(recorded) {
    const values = new Map();
    for (const [key, value] of Object.entries(recorded)) {
      const address = this.#addresses.get(key);
      if (!address) continue;
      if (!values.has(address.model)) values.set(address.model, new Map());
      values.get(address.model).set(address.joint, value);
    }
    return values;
  }

  /**
   * @param {number} frame A frame.
   * @returns {Array<number>|null} The robot's root pose, or null when not recorded.
   */
  robotPose(frame) {
    return this.#trajectory[TrajectoryKey.BASE]?.[frame] ?? null;
  }

  /**
   * @param {number} frame A frame.
   * @returns {Map<string, Array<number>>} The root pose of each robot instance.
   */
  instancePoses(frame) {
    return new Map(Object.entries(this.#trajectory[TrajectoryKey.MODEL_BASES]?.[frame] ?? {}));
  }

  /**
   * @param {number} frame A frame.
   * @returns {Map<string, Array<number>>} The pose of each free object that has one.
   */
  objectPoses(frame) {
    const poses = Object.entries(this.#trajectory[TrajectoryKey.OBJECTS]?.[frame] ?? {});
    return new Map(poses.filter(([, pose]) => Array.isArray(pose)));
  }

  /**
   * @param {number} frame A frame.
   * @returns {number} The position of the step the frame belongs to, -1 for none.
   */
  segmentAt(frame) {
    return this.#segments.findIndex((segment) => segment[SegmentKey.START] <= frame && frame <= segment[SegmentKey.END]);
  }
}

/**
 * @param {Array<Object>} models The scene's model descriptions.
 * @returns {Map<string, JointAddress>} The address of every movable joint by its trajectory key.
 */
function addressesOf(models) {
  const addresses = new Map();
  for (const model of models) {
    const prefix = model[ModelKey.PREFIX] ?? '';
    for (const joint of model[ModelKey.MOVABLE_JOINTS] ?? []) {
      const key = prefix ? `${prefix}${PREFIX_SEPARATOR}${joint}` : joint;
      addresses.set(key, new JointAddress(model[ModelKey.NAME], joint));
    }
  }
  return addresses;
}
