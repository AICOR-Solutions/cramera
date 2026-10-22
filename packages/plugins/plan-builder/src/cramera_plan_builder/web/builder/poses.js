/**
 * Poses as the protocol writes them, `[x, y, z, qx, qy, qz, qw]` in metres and a unit
 * quaternion, and the position and heading a person edits.
 */

/**
 * Where each number sits in a pose.
 */
export const PoseIndex = Object.freeze({ X: 0, Y: 1, Z: 2, QX: 3, QY: 4, QZ: 5, QW: 6 });

/**
 * How many numbers a position has.
 */
const POSITION_LENGTH = 3;

/**
 * How many decimal places an edited coordinate keeps.
 */
const COORDINATE_DECIMALS = 3;

/**
 * Degrees in a half turn, to convert headings for people.
 */
const HALF_TURN_DEGREES = 180;

// %% poses

export class PlanPose {
  /**
   * @param {number} x The x coordinate in metres.
   * @param {number} y The y coordinate in metres.
   * @param {number} z The z coordinate in metres.
   * @param {number} yaw The heading about the z axis in radians.
   * @returns {Array<number>} The pose with only a heading.
   */
  static of(x, y, z, yaw) {
    return [x, y, z, 0, 0, Math.sin(yaw / 2), Math.cos(yaw / 2)];
  }

  /**
   * @param {Array<number>} pose A pose.
   * @returns {Array<number>} Its position.
   */
  static position(pose) {
    return pose.slice(0, POSITION_LENGTH);
  }

  /**
   * @param {Array<number>} pose A pose.
   * @returns {Array<number>} Its orientation as `[qx, qy, qz, qw]`.
   */
  static orientation(pose) {
    return pose.slice(POSITION_LENGTH);
  }

  /**
   * @param {Array<number>} pose A pose.
   * @returns {number} Its heading about the z axis in radians.
   */
  static yaw(pose) {
    const [x, y, z, w] = PlanPose.orientation(pose);
    return Math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z));
  }

  /**
   * @param {Array<number>} pose A pose.
   * @param {Array<number>} position The new position.
   * @returns {Array<number>} The pose at the position, its orientation kept.
   */
  static moved(pose, position) {
    return [...position.map(PlanPose.rounded), ...PlanPose.orientation(pose)];
  }

  /**
   * @param {Array<number>} pose A pose.
   * @param {number} yaw The new heading in radians.
   * @returns {Array<number>} The pose turned to the heading, upright, its position kept.
   */
  static turned(pose, yaw) {
    return PlanPose.of(...PlanPose.position(pose), yaw);
  }

  /**
   * @param {number} value A coordinate.
   * @returns {number} The coordinate to the decimals a person edits.
   */
  static rounded(value) {
    const scale = 10 ** COORDINATE_DECIMALS;
    return Math.round(value * scale) / scale;
  }

  /**
   * @param {number} radians An angle.
   * @returns {number} The angle in whole degrees.
   */
  static degrees(radians) {
    return Math.round((radians * HALF_TURN_DEGREES) / Math.PI);
  }

  /**
   * @param {number} degrees An angle.
   * @returns {number} The angle in radians.
   */
  static radians(degrees) {
    return (degrees * Math.PI) / HALF_TURN_DEGREES;
  }

  /**
   * @param {*} value A decoded JSON value.
   * @returns {boolean} Whether it is a pose of finite numbers.
   */
  static isPose(value) {
    return Array.isArray(value) && value.length === Object.keys(PoseIndex).length && value.every(Number.isFinite);
  }
}
